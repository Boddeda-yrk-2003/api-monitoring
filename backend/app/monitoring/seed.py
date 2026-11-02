"""
Bootstrap: endpoint catalogue + 24h of realistic demo history.

Running this makes the dashboard immediately meaningful (charts, uptime strips,
resolved incidents with RCA, alert history) instead of an empty screen.
Set SEED_HISTORY_ON_STARTUP=false to start from a clean database.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    Check,
    Endpoint,
    ErrorLog,
    Incident,
    RequestLog,
    SettingKV,
)
from app.monitoring import rca
from app.monitoring.engine import RULE_SEVERITY, _channels_for, _new_public_id

random.seed(20240607)

# --------------------------------------------------------------------------- #
# Endpoint catalogue
# --------------------------------------------------------------------------- #
ENDPOINTS: list[dict] = [
    {
        "name": "Health Check",
        "path": "/health",
        "method": "GET",
        "group_name": "core",
        "description": "Liveness/readiness probe used by the load balancer and the monitor.",
        "expected_status": 200,
        "latency_threshold_ms": 1000.0,
        "criticality": "critical",
        "enabled": True,
        "base_latency": 12.0,
    },
    {
        "name": "List Users",
        "path": "/users",
        "method": "GET",
        "group_name": "core",
        "description": "Returns the sample user collection (business endpoint).",
        "expected_status": 200,
        "latency_threshold_ms": 3000.0,
        "criticality": "high",
        "enabled": True,
        "base_latency": 45.0,
    },
    {
        "name": "List Products",
        "path": "/products",
        "method": "GET",
        "group_name": "core",
        "description": "Returns the sample product catalogue (business endpoint).",
        "expected_status": 200,
        "latency_threshold_ms": 3000.0,
        "criticality": "high",
        "enabled": True,
        "base_latency": 62.0,
    },
    {
        "name": "Secure Data",
        "path": "/secure-data",
        "method": "GET",
        "group_name": "security",
        "description": "API-key protected resource - 401 when the key is missing or invalid.",
        "expected_status": 200,
        "latency_threshold_ms": 3000.0,
        "criticality": "high",
        "enabled": True,
        "base_latency": 28.0,
    },
    # ---- chaos endpoints: intentionally NOT probed continuously
    {
        "name": "Simulate Server Error",
        "path": "/simulate-error",
        "method": "GET",
        "group_name": "chaos",
        "description": "Raises an unhandled exception -> HTTP 500 (chaos / game-day endpoint).",
        "expected_status": 500,
        "latency_threshold_ms": 3000.0,
        "criticality": "low",
        "enabled": False,
        "base_latency": 20.0,
    },
    {
        "name": "Simulate Timeout",
        "path": "/simulate-timeout",
        "method": "GET",
        "group_name": "chaos",
        "description": "Sleeps N seconds to simulate a slow dependency (chaos endpoint).",
        "expected_status": 200,
        "latency_threshold_ms": 3000.0,
        "criticality": "low",
        "enabled": False,
        "base_latency": 6000.0,
    },
    {
        "name": "Simulate Rate Limit",
        "path": "/simulate-rate-limit",
        "method": "GET",
        "group_name": "chaos",
        "description": "Returns 429 once the request quota for the window is exhausted.",
        "expected_status": 200,
        "latency_threshold_ms": 3000.0,
        "criticality": "low",
        "enabled": False,
        "base_latency": 18.0,
    },
    {
        "name": "Simulate Auth Error",
        "path": "/simulate-auth-error",
        "method": "GET",
        "group_name": "chaos",
        "description": "Always returns 401 (chaos endpoint for the auth failure scenario).",
        "expected_status": 401,
        "latency_threshold_ms": 3000.0,
        "criticality": "low",
        "enabled": False,
        "base_latency": 15.0,
    },
]

# --------------------------------------------------------------------------- #
# Injected incident windows (hours_ago, duration_min, endpoint, rule, status)
# --------------------------------------------------------------------------- #
INCIDENT_WINDOWS = [
    {"hours_ago": 19.5, "minutes": 22, "path": "/users", "rule": "SERVER_ERROR", "status": 500},
    {"hours_ago": 11.0, "minutes": 35, "path": "/products", "rule": "SLOW_RESPONSE", "status": 200, "slow": True},
    {"hours_ago": 6.5, "minutes": 14, "path": "/products", "rule": "RATE_LIMIT", "status": 429},
    {"hours_ago": 2.2, "minutes": 9, "path": "/secure-data", "rule": "AUTH_FAILURE", "status": 401},
    {"hours_ago": 0.9, "minutes": 4, "path": "/health", "rule": "SERVER_ERROR", "status": 503},
]


def utcnow() -> datetime:
    return datetime.utcnow()


def seed_endpoints(db: Session) -> list[Endpoint]:
    created: list[Endpoint] = []
    for spec in ENDPOINTS:
        ep = db.query(Endpoint).filter(Endpoint.path == spec["path"]).first()
        if ep is None:
            ep = Endpoint(**{k: v for k, v in spec.items() if k != "base_latency"})
            db.add(ep)
            created.append(ep)
    db.commit()
    return db.query(Endpoint).order_by(Endpoint.id).all()


def _latency(base: float, ts: datetime, rng: random.Random) -> float:
    """Diurnal traffic pattern + jitter, occasional micro-spike."""
    hour = ts.hour + ts.minute / 60
    diurnal = 1 + 0.35 * math.sin((hour - 8) / 24 * 2 * math.pi)
    jitter = rng.uniform(0.75, 1.3)
    value = base * diurnal * jitter
    if rng.random() < 0.004:  # rare micro spike
        value *= rng.uniform(2.0, 3.5)
    return round(max(3.0, value), 2)


def _window_active(ts: datetime, spec: dict) -> bool:
    start = utcnow() - timedelta(hours=spec["hours_ago"])
    return start <= ts <= start + timedelta(minutes=spec["minutes"])


def seed_history(db: Session, hours: int = 24, step_seconds: int = 60) -> dict:
    endpoints = seed_endpoints(db)
    if db.query(Check).count() > 0:
        return {"status": "skipped", "reason": "history already seeded"}

    rng = random.Random(4242)
    now = utcnow()
    start = now - timedelta(hours=hours)
    base_by_path = {e["path"]: e["base_latency"] for e in ENDPOINTS}

    # ------------------------------------------------------------ checks
    checks: list[Check] = []
    ts = start
    while ts <= now:
        for ep in endpoints:
            if not ep.enabled:
                continue
            base = base_by_path.get(ep.path, 40.0)
            latency = _latency(base, ts, rng)
            ok, status, err_type, msg = True, 200, "none", ""
            for spec in INCIDENT_WINDOWS:
                if spec["path"] != ep.path or not _window_active(ts, spec):
                    continue
                if spec.get("slow"):
                    latency = round(latency * rng.uniform(12, 22), 2)
                    ok, status, err_type, msg = True, 200, "none", "latency above SLO"
                else:
                    if rng.random() < 0.85:
                        ok = False
                        status = spec["status"]
                        err_type = "http_error"
                        msg = f"unexpected status {status}"
                        latency = round(latency * rng.uniform(1.2, 2.0), 2)
            checks.append(
                Check(
                    endpoint_id=ep.id,
                    checked_at=ts,
                    ok=ok,
                    status_code=status,
                    latency_ms=latency,
                    error_type=err_type,
                    error_message=msg,
                    request_id=f"seed-{rng.randrange(10**10, 10**11)}",
                    source="synthetic",
                )
            )
        ts += timedelta(seconds=step_seconds)

    db.bulk_save_objects(checks)
    db.commit()

    # ------------------------------------------------- real traffic logs
    paths = ["/health", "/users", "/products", "/secure-data", "/users/1", "/simulate-error", "/simulate-rate-limit"]
    logs: list[RequestLog] = []
    ts = start
    while ts <= now:
        hour = ts.hour
        volume = max(1, int(rng.gauss(6, 2) * (1 + 0.4 * math.sin((hour - 9) / 24 * 2 * math.pi))))
        for _ in range(volume):
            path = rng.choices(paths, weights=[20, 32, 28, 13, 5, 1, 1], k=1)[0]
            status, latency = 200, round(rng.uniform(8, 120), 2)
            if path == "/simulate-error" and rng.random() < 0.9:
                status = 500
            elif path == "/simulate-rate-limit" and rng.random() < 0.12:
                status = 429
            elif path.startswith("/users/") and rng.random() < 0.12:
                status = 404
            for spec in INCIDENT_WINDOWS:
                if spec["path"] == path and _window_active(ts, spec) and rng.random() < 0.55:
                    status = spec["status"]
                    if spec.get("slow"):
                        latency = round(rng.uniform(3200, 5200), 2)
            logs.append(
                RequestLog(
                    ts=ts,
                    method="GET",
                    path=path,
                    status_code=status,
                    latency_ms=latency,
                    request_id=f"seed-{rng.randrange(10**10, 10**11)}",
                    client_ip=f"10.0.{rng.randint(0, 5)}.{rng.randint(2, 250)}",
                    user_agent="seed-generator/1.0",
                    is_error=status >= 400,
                )
            )
        ts += timedelta(seconds=30)
    db.bulk_save_objects(logs)
    db.commit()

    # ------------------------------------------ incidents + alerts + errors
    incidents_created = 0
    alerts_created = 0
    for spec in INCIDENT_WINDOWS:
        ep = db.query(Endpoint).filter(Endpoint.path == spec["path"]).first()
        detected = utcnow() - timedelta(hours=spec["hours_ago"])
        resolved = detected + timedelta(minutes=spec["minutes"])
        rule = spec["rule"]
        severity = RULE_SEVERITY.get(rule, "warning")

        # a captured exception for server errors (root cause evidence)
        if rule in ("SERVER_ERROR",):
            db.add(
                ErrorLog(
                    ts=detected,
                    request_id=f"seed-{rng.randrange(10**10, 10**11)}",
                    method="GET",
                    path=spec["path"],
                    exception_type="RuntimeError" if spec["path"] != "/health" else "DependencyUnavailable",
                    exception_message=(
                        "Simulated upstream failure: inventory service returned no data"
                        if spec["path"] == "/users"
                        else "Readiness dependency 'cache' failed health probe"
                    ),
                    traceback=(
                        'Traceback (most recent call last):\n'
                        f'  File "app/routers/sample.py", line 118, in {spec["path"].strip("/").replace("-", "_")}\n'
                        '    raise RuntimeError("Simulated upstream failure")\n'
                        'RuntimeError: Simulated upstream failure\n'
                    ),
                    status_code=spec["status"],
                    client_ip="10.0.1.42",
                    latency_ms=round(rng.uniform(120, 640), 2),
                )
            )

        analysis = rca.analyse(
            rule_id=rule,
            status_code=spec["status"],
            error_type="none",
            latency_ms=(rng.uniform(3200, 4800) if spec.get("slow") else rng.uniform(150, 900)),
            threshold_ms=ep.latency_threshold_ms if ep else 3000.0,
            path=spec["path"],
            method="GET",
            db=db,
        )
        inc = Incident(
            public_id=_new_public_id(),
            endpoint_id=ep.id if ep else None,
            endpoint_path=spec["path"],
            rule_id=rule,
            title=f"{rca.RULE_CATALOG.get(rule, {}).get('title', rule)} on {spec['path']}",
            severity=severity,
            status="resolved",
            category=analysis["category"],
            http_status=spec["status"],
            latency_ms=round(rng.uniform(3200, 4800), 2) if spec.get("slow") else round(rng.uniform(150, 900), 2),
            error_type="none",
            root_cause=analysis["root_cause"],
            root_cause_confidence=analysis["root_cause_confidence"],
            probable_causes=analysis["probable_causes"],
            evidence={**analysis["evidence"], "seeded": True, "detection": "synthetic probe"},
            recommended_actions=analysis["recommended_actions"],
            owner_team=analysis["owner_team"],
            detected_at=detected,
            last_seen_at=resolved,
            resolved_at=resolved,
            occurrences=rng.randint(3, 26),
            duration_seconds=(resolved - detected).total_seconds(),
        )
        db.add(inc)
        db.flush()
        incidents_created += 1

        for channel in _channels_for(severity):
            db.add(
                Alert(
                    incident_id=inc.id,
                    created_at=detected,
                    channel=channel,
                    destination={
                        "slack": "#api-alerts (DRY-RUN)",
                        "email": "sre-oncall@example.com (DRY-RUN)",
                        "call": "+91XXXXXXXXXX (DRY-RUN)",
                    }[channel],
                    subject=inc.title,
                    body=f"{inc.root_cause}\n\nOwner: {inc.owner_team}",
                    payload={"incident": inc.public_id, "rule": rule, "seeded": True},
                    status="simulated",
                    delivery_note="Seeded demo history - rendered payload stored as DRY-RUN proof.",
                    severity=severity,
                )
            )
            alerts_created += 1

    db.commit()

    # Park the live-traffic cursor past the generated history so seeded rows are
    # never re-evaluated by the monitor as if they were fresh failures.
    max_log_id = db.query(func.max(RequestLog.id)).scalar() or 0
    marker = db.get(SettingKV, "live_eval_last_id")
    if marker is None:
        db.add(SettingKV(key="live_eval_last_id", value=str(max_log_id)))
    else:
        marker.value = str(max_log_id)
    db.commit()

    return {
        "status": "seeded",
        "checks": len(checks),
        "request_logs": len(logs),
        "incidents": incidents_created,
        "alerts": alerts_created,
        "hours": hours,
    }
