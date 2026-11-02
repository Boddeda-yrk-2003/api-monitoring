"""
Monitoring control-plane API consumed by the React dashboard.

    GET  /monitor/summary            KPI rollup
    GET  /monitor/timeseries         latency / error trend
    GET  /monitor/endpoints          per-endpoint health
    GET  /monitor/incidents          incidents + root cause analysis
    GET  /monitor/alerts             notification history / proof
    GET  /monitor/errors             captured exceptions (RCA evidence)
    POST /monitor/probe/now          force a monitoring cycle
    POST /monitor/simulate/{name}    run a failure scenario end-to-end
    GET  /monitor/settings           thresholds + notification channels
    PUT  /monitor/settings           update runtime configuration
    POST /monitor/notifications/test send a test alert to a channel
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import get_db
from app.models import Alert, Check, Endpoint, ErrorLog, Incident, RequestLog, SettingKV
from app.monitoring import alerter, analytics, engine, metrics
from app.monitoring.engine import RULE_SEVERITY
from app.schemas import (
    AlertOut,
    ChannelTestResult,
    CheckOut,
    EndpointStats,
    ErrorLogOut,
    IncidentOut,
    SettingsOut,
    SimulationResult,
    SummaryOut,
    TimeSeriesPoint,
)

router = APIRouter(prefix="/monitor", tags=["Monitoring"])

# --------------------------------------------------------------------------- #
# Failure lab catalogue
# --------------------------------------------------------------------------- #
SCENARIOS: dict[str, dict[str, Any]] = {
    "auth": {
        "title": "Invalid API authentication",
        "endpoint": "/secure-data",
        "method": "GET",
        "description": "Calls the protected resource without the X-API-Key header.",
        "expected_rule": "AUTH_FAILURE",
        "expected_status": 401,
        "expected_detection": "HTTP 401 detected, authentication error classified, alert triggered.",
    },
    "timeout": {
        "title": "API timeout",
        "endpoint": "/simulate-timeout?seconds=12",
        "method": "GET",
        "description": "Requests an endpoint that sleeps 12s; the client aborts after 8s.",
        "expected_rule": "TIMEOUT",
        "expected_status": None,
        "expected_detection": "Slow response detected, timeout classified (critical), alert triggered.",
    },
    "server_error": {
        "title": "Server error (HTTP 500)",
        "endpoint": "/simulate-error",
        "method": "GET",
        "description": "Triggers an unhandled exception inside the API.",
        "expected_rule": "SERVER_ERROR",
        "expected_status": 500,
        "expected_detection": "HTTP 500 detected, exception + traceback captured, RCA produced.",
    },
    "rate_limit": {
        "title": "Rate limit exceeded (HTTP 429)",
        "endpoint": "/simulate-rate-limit",
        "method": "GET",
        "description": f"Fires {settings.RATE_LIMIT_MAX_REQUESTS + 2} requests to exhaust the per-minute quota.",
        "expected_rule": "RATE_LIMIT",
        "expected_status": 429,
        "expected_detection": "HTTP 429 detected, rate-limit issue classified, alert triggered.",
    },
    "slow_response": {
        "title": "Latency SLO breach (> 3s)",
        "endpoint": "/simulate-timeout?seconds=3.5",
        "method": "GET",
        "description": "Requests a 3.5s response, above the 3000 ms latency SLO.",
        "expected_rule": "SLOW_RESPONSE",
        "expected_status": 200,
        "expected_detection": "p50 latency above threshold detected, warning alert triggered.",
    },
    "health_failure": {
        "title": "Service health check failure",
        "endpoint": "/health?degraded=true",
        "method": "GET",
        "description": "Forces /health to report an unhealthy dependency (HTTP 503).",
        "expected_rule": "HEALTH_CHECK_FAILED",
        "expected_status": 503,
        "expected_detection": "Health probe fails, service marked unhealthy, critical alert triggered.",
    },
    "downtime": {
        "title": "API downtime (connection refused)",
        "endpoint": "http://127.0.0.1:9/health",
        "method": "GET",
        "description": "Probes a closed port to simulate the service being unreachable.",
        "expected_rule": "API_DOWN",
        "expected_status": None,
        "expected_detection": "Connection refused detected, endpoint marked down, critical alert + call triggered.",
    },
}


def _incident_out(db: Session, inc: Incident) -> IncidentOut:
    channels = [c for (c,) in db.query(Alert.channel).filter(Alert.incident_id == inc.id).distinct().all()]
    alert_count = db.query(func.count(Alert.id)).filter(Alert.incident_id == inc.id).scalar() or 0
    data = IncidentOut.model_validate(inc)
    data.alert_count = int(alert_count)
    data.channels = channels
    return data


# --------------------------------------------------------------------------- #
# Dashboard reads
# --------------------------------------------------------------------------- #
@router.get("/summary", response_model=SummaryOut, summary="Dashboard KPI rollup")
def get_summary(window: str = Query("24h"), db: Session = Depends(get_db)) -> Any:
    data = analytics.summary(db, window)
    data["monitor_running"] = engine.engine.running
    return SummaryOut(**data)


@router.get("/timeseries", response_model=list[TimeSeriesPoint], summary="Latency & error trend")
def get_timeseries(
    window: str = Query("24h"),
    endpoint_id: int | None = Query(None),
    db: Session = Depends(get_db),
) -> Any:
    return analytics.timeseries(db, window, endpoint_id)


@router.get("/endpoints", response_model=list[EndpointStats], summary="Per-endpoint health")
def get_endpoints(window: str = Query("24h"), db: Session = Depends(get_db)) -> Any:
    return analytics.endpoint_stats(db, window)


@router.get("/endpoints/{endpoint_id}/uptime", summary="Uptime strip for one endpoint")
def get_uptime(endpoint_id: int, hours: int = Query(24), db: Session = Depends(get_db)) -> Any:
    return analytics.uptime_timeline(db, endpoint_id, hours=hours)


@router.get("/endpoints/{endpoint_id}/checks", response_model=list[CheckOut], summary="Recent probe results")
def get_checks(endpoint_id: int, limit: int = Query(100, le=500), db: Session = Depends(get_db)) -> Any:
    rows = (
        db.query(Check, Endpoint.path)
        .join(Endpoint, Endpoint.id == Check.endpoint_id)
        .filter(Check.endpoint_id == endpoint_id)
        .order_by(Check.id.desc())
        .limit(limit)
        .all()
    )
    out = []
    for check, path in rows:
        item = CheckOut.model_validate(check)
        item.endpoint_path = path
        out.append(item)
    return out


@router.get("/traffic", summary="Real inbound traffic by path")
def get_traffic(window: str = Query("24h"), db: Session = Depends(get_db)) -> Any:
    return {
        "by_path": analytics.traffic_by_path(db, window),
        "by_status": analytics.status_breakdown(db, window),
    }


@router.get("/incidents", response_model=list[IncidentOut], summary="Incidents with root cause analysis")
def get_incidents(
    status: str = Query("all", pattern="^(all|open|acknowledged|resolved)$"),
    severity: str = Query("all"),
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
) -> Any:
    q = db.query(Incident)
    if status != "all":
        q = q.filter(Incident.status == status)
    if severity != "all":
        q = q.filter(Incident.severity == severity)
    rows = q.order_by(Incident.detected_at.desc()).limit(limit).all()
    return [_incident_out(db, r) for r in rows]


@router.get("/incidents/{incident_id}", response_model=IncidentOut, summary="Single incident")
def get_incident(incident_id: int, db: Session = Depends(get_db)) -> Any:
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    return _incident_out(db, inc)


@router.post("/incidents/{incident_id}/acknowledge", summary="Acknowledge an incident")
def acknowledge(incident_id: int, db: Session = Depends(get_db)) -> Any:
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    inc.status = "acknowledged"
    db.commit()
    return _incident_out(db, inc)


@router.post("/incidents/{incident_id}/resolve", summary="Manually resolve an incident")
def resolve(incident_id: int, db: Session = Depends(get_db)) -> Any:
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    engine.engine._resolve(db, inc)
    return _incident_out(db, inc)


@router.get("/alerts", response_model=list[AlertOut], summary="Alert notification history")
def get_alerts(limit: int = Query(60, le=500), channel: str = Query("all"), db: Session = Depends(get_db)) -> Any:
    q = db.query(Alert).order_by(Alert.id.desc())
    if channel != "all":
        q = q.filter(Alert.channel == channel)
    rows = q.limit(limit).all()
    out = []
    for a in rows:
        item = AlertOut.model_validate(a)
        if a.incident_id:
            inc = db.get(Incident, a.incident_id)
            item.incident_title = inc.title if inc else ""
        out.append(item)
    return out


@router.get("/alerts/outbox", summary="Raw alert outbox files (notification proof)")
def get_outbox(limit: int = Query(40, le=500)) -> Any:
    import json
    from pathlib import Path

    outbox = alerter.OUTBOX_DIR
    lines: list[dict[str, Any]] = []
    files = sorted(outbox.glob("alerts-*.jsonl"), reverse=True)
    for f in files:
        with f.open(encoding="utf-8") as fh:
            for line in fh.readlines()[-limit:]:
                try:
                    lines.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
    return {"file": str(outbox), "count": len(lines), "items": list(reversed(lines))[:limit]}


@router.get("/errors", response_model=list[ErrorLogOut], summary="Captured exceptions (RCA evidence)")
def get_errors(limit: int = Query(50, le=500), db: Session = Depends(get_db)) -> Any:
    return db.query(ErrorLog).order_by(ErrorLog.id.desc()).limit(limit).all()


@router.get("/engine/status", summary="Monitor engine status")
def engine_status() -> Any:
    return engine.engine.status()


# --------------------------------------------------------------------------- #
# Control actions
# --------------------------------------------------------------------------- #
@router.post("/probe/now", summary="Run one monitoring cycle immediately")
async def probe_now() -> Any:
    started = time.time()
    results = await engine.engine.run_cycle()
    return {
        "ran": len(results),
        "duration_ms": round((time.time() - started) * 1000, 2),
        "results": results,
        "engine": engine.engine.status(),
    }


@router.get("/scenarios", summary="Failure lab catalogue")
def list_scenarios() -> Any:
    return [
        {"id": k, **{kk: vv for kk, vv in v.items() if kk != "description"}, "description": v["description"]}
        for k, v in SCENARIOS.items()
    ]


@router.post("/simulate/{scenario}", response_model=SimulationResult, summary="Run a failure scenario end-to-end")
async def simulate(scenario: str, db: Session = Depends(get_db)) -> Any:
    spec = SCENARIOS.get(scenario)
    if not spec:
        raise HTTPException(404, f"unknown scenario '{scenario}' (available: {', '.join(SCENARIOS)})")

    started = time.time()
    status_code: int | None = None
    latency_ms = 0.0
    error_type = "none"
    error_message = ""
    request_id = f"lab-{uuid.uuid4().hex[:12]}"
    raw: dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=3.0)) as client:
        url = spec["endpoint"]
        if not url.startswith("http"):
            url = f"{settings.SELF_BASE_URL.rstrip('/')}{url}"
        try:
            if scenario == "rate_limit":
                # Exhaust the quota, keep the last (429) response.
                last: httpx.Response | None = None
                for _ in range(settings.RATE_LIMIT_MAX_REQUESTS + 2):
                    last = await client.get(url, headers={"X-Request-ID": request_id})
                resp = last
            elif scenario == "timeout":
                # Client budget (8s) < server sleep (12s) -> genuine client timeout.
                resp = await client.get(url, timeout=8.0, headers={"X-Request-ID": request_id})
            else:
                resp = await client.get(url, headers={"X-Request-ID": request_id})

            latency_ms = round(float(resp.elapsed.total_seconds()) * 1000, 2)
            status_code = resp.status_code
            try:
                raw = resp.json()
            except Exception:  # noqa: BLE001
                raw = {"text": resp.text[:400]}
            request_id = resp.headers.get("x-request-id", request_id)
        except httpx.TimeoutException:
            latency_ms = round((time.time() - started) * 1000, 2)
            error_type = "timeout"
            error_message = "request aborted: exceeded the 8s client timeout (server still processing)"
            status_code = None
            raw = {"error": "timeout", "detail": error_message}
        except httpx.ConnectError as exc:
            latency_ms = round((time.time() - started) * 1000, 2)
            error_type = "connection"
            error_message = f"connection refused: {exc}"
            status_code = None
            raw = {"error": "connection_refused", "detail": error_message}
        except Exception as exc:  # noqa: BLE001
            latency_ms = round((time.time() - started) * 1000, 2)
            error_type = "connection"
            error_message = f"{type(exc).__name__}: {exc}"
            raw = {"error": type(exc).__name__, "detail": error_message}

    # --------------------------------------------- deterministic detection
    last_alert_id = db.query(func.max(Alert.id)).scalar() or 0
    # Close the implicit read transaction so the queries below (and the
    # incident lookup) observe the rows written by the detection engine, which
    # runs on its own short-lived session.
    db.commit()
    detection_started = time.time()
    incident_ids = await run_in_threadpool(
        engine.engine.record_manual_result,
        path=spec["endpoint"].split("?")[0],
        method=spec["method"],
        status_code=status_code,
        latency_ms=latency_ms,
        error_type=error_type,
        error_message=error_message or (f"HTTP {status_code}" if status_code else ""),
        request_id=request_id,
        rule_override=spec["expected_rule"],
        source="failure-lab",
    )
    detection_ms = round((time.time() - detection_started) * 1000, 2)

    incident = db.get(Incident, incident_ids[0]) if incident_ids else None
    alerts: list[Alert] = []
    if incident is not None:
        alerts = (
            db.query(Alert)
            .filter(Alert.incident_id == incident.id, Alert.id > last_alert_id)
            .order_by(Alert.id.desc())
            .limit(6)
            .all()
        )
        for a in alerts:
            metrics.observe_alert(a.channel, a.status)

    return SimulationResult(
        scenario=scenario,
        title=spec["title"],
        endpoint=spec["endpoint"],
        http_status=status_code,
        latency_ms=latency_ms,
        expected_detection=spec["expected_detection"],
        detected=incident is not None,
        detection_latency_ms=detection_ms,
        incident=_incident_out(db, incident) if incident else None,
        alerts=[AlertOut.model_validate(a) for a in alerts],
        message=(
            f"Scenario '{scenario}' executed in {latency_ms:.0f} ms -> rule {spec['expected_rule']} fired, "
            f"{len(alerts)} notification(s) dispatched."
            if incident
            else f"Scenario '{scenario}' executed but no incident was raised."
        ),
        raw_response=raw,
    )


# --------------------------------------------------------------------------- #
# Settings + channel tests
# --------------------------------------------------------------------------- #
SETTING_MAP: dict[str, str] = {
    "latency_threshold_ms": "LATENCY_THRESHOLD_MS",
    "error_rate_threshold_pct": "ERROR_RATE_THRESHOLD_PCT",
    "error_rate_window_minutes": "ERROR_RATE_WINDOW_MINUTES",
    "downtime_consecutive_failures": "DOWNTIME_CONSECUTIVE_FAILURES",
    "recovery_consecutive_successes": "RECOVERY_CONSECUTIVE_SUCCESSES",
    "alert_cooldown_seconds": "ALERT_COOLDOWN_SECONDS",
    "probe_interval_seconds": "PROBE_INTERVAL_SECONDS",
    "rate_limit_max_requests": "RATE_LIMIT_MAX_REQUESTS",
    "simulated_timeout_seconds": "SIMULATED_TIMEOUT_SECONDS",
    "slack_webhook_url": "SLACK_WEBHOOK_URL",
    "slack_channel_label": "SLACK_CHANNEL_LABEL",
    "smtp_host": "SMTP_HOST",
    "smtp_port": "SMTP_PORT",
    "smtp_username": "SMTP_USERNAME",
    "smtp_password": "SMTP_PASSWORD",
    "alert_email_from": "ALERT_EMAIL_FROM",
    "alert_email_to": "ALERT_EMAIL_TO",
    "twilio_account_sid": "TWILIO_ACCOUNT_SID",
    "twilio_auth_token": "TWILIO_AUTH_TOKEN",
    "twilio_from_number": "TWILIO_FROM_NUMBER",
    "alert_call_to_number": "ALERT_CALL_TO_NUMBER",
}

NUMERIC_KEYS = {
    "latency_threshold_ms": float,
    "error_rate_threshold_pct": float,
    "simulated_timeout_seconds": float,
}


@router.get("/settings", response_model=SettingsOut, summary="Thresholds & notification channels")
def get_settings(db: Session = Depends(get_db)) -> Any:
    overrides = {
        row.key: row.value
        for row in db.query(SettingKV).filter(SettingKV.key != "live_eval_last_id").all()
    }
    return SettingsOut(
        latency_threshold_ms=settings.LATENCY_THRESHOLD_MS,
        error_rate_threshold_pct=settings.ERROR_RATE_THRESHOLD_PCT,
        error_rate_window_minutes=settings.ERROR_RATE_WINDOW_MINUTES,
        downtime_consecutive_failures=settings.DOWNTIME_CONSECUTIVE_FAILURES,
        recovery_consecutive_successes=settings.RECOVERY_CONSECUTIVE_SUCCESSES,
        alert_cooldown_seconds=settings.ALERT_COOLDOWN_SECONDS,
        probe_interval_seconds=settings.PROBE_INTERVAL_SECONDS,
        rate_limit_max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
        simulated_timeout_seconds=settings.SIMULATED_TIMEOUT_SECONDS,
        channels={
            "slack": settings.slack_enabled,
            "email": settings.email_enabled,
            "call": settings.call_enabled,
        },
        channel_targets={
            "slack": settings.SLACK_CHANNEL_LABEL if settings.slack_enabled else "not configured (dry-run)",
            "email": settings.ALERT_EMAIL_TO if settings.email_enabled else "not configured (dry-run)",
            "call": settings.ALERT_CALL_TO_NUMBER if settings.call_enabled else "not configured (dry-run)",
        },
    )


@router.put("/settings", response_model=SettingsOut, summary="Update thresholds / channels at runtime")
def update_settings(payload: dict[str, Any], db: Session = Depends(get_db)) -> Any:
    for key, value in payload.items():
        if key not in SETTING_MAP:
            raise HTTPException(400, f"unknown setting '{key}'")
        attr = SETTING_MAP[key]
        coerced: Any = value
        if key in NUMERIC_KEYS:
            coerced = NUMERIC_KEYS[key](value)
        elif key == "smtp_port":
            coerced = int(value)
        setattr(settings, attr, coerced)
        row = db.get(SettingKV, key)
        if row is None:
            db.add(SettingKV(key=key, value=str(value)))
        else:
            row.value = str(value)
    db.commit()
    return get_settings(db)


@router.post("/notifications/test", response_model=list[ChannelTestResult], summary="Send a test alert")
def test_notifications(
    channels: str = Query("slack,email,call"),
    db: Session = Depends(get_db),
) -> Any:
    fake = Incident(
        id=None,  # type: ignore[arg-type]
        public_id=f"TEST-{uuid.uuid4().hex[:6].upper()}",
        endpoint_path="/monitor/notifications/test",
        rule_id="TEST",
        title="APIGuard test alert - notification channel verification",
        severity="warning",
        status="open",
        category="test",
        http_status=200,
        latency_ms=0.0,
        root_cause="Manual channel verification triggered from the dashboard (no real failure).",
        root_cause_confidence="high",
        probable_causes=["Operator requested a delivery test."],
        evidence={"triggered_by": "dashboard", "environment": settings.ENVIRONMENT},
        recommended_actions=["No action required - this is a delivery test."],
        owner_team="Platform / SRE",
        detected_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
        occurrences=1,
    )
    requested = [c.strip() for c in channels.split(",") if c.strip()]
    alerts = alerter.dispatch(db, fake, channels=requested, note="Test alert requested from the dashboard.")
    for a in alerts:
        metrics.observe_alert(a.channel, a.status)

    results = []
    for a in alerts:
        configured = {
            "slack": settings.slack_enabled,
            "email": settings.email_enabled,
            "call": settings.call_enabled,
        }.get(a.channel, False)
        results.append(
            ChannelTestResult(
                channel=a.channel,
                configured=configured,
                status=a.status,
                destination=a.destination,
                note=a.delivery_note,
                payload=a.payload,
            )
        )
    return results
