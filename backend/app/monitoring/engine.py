"""
Monitoring engine: synthetic probing, rule evaluation, incident lifecycle and
alert triggering.

The engine runs as an asyncio background task inside the FastAPI process:

    probe -> persist check -> evaluate alert rules
                                    |-> open / update / resolve incidents
                                    |-> run RCA engine
                                    |-> dispatch notifications (Slack / Email / Call)

Real inbound traffic is evaluated as well (`evaluate_live_traffic`) so failures
triggered manually from the Failure Lab are detected immediately.
"""
from __future__ import annotations

import asyncio
import random
import traceback as tb_module
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import SessionLocal
from app.models import Check, Endpoint, Incident, RequestLog, SettingKV
from app.monitoring import metrics, rca
from app.monitoring.alerter import dispatch

# --------------------------------------------------------------------------- #
# Alert rules
# --------------------------------------------------------------------------- #
RULE_SEVERITY: dict[str, str] = {
    "API_DOWN": "critical",
    "SERVER_ERROR": "critical",
    "TIMEOUT": "critical",
    "HEALTH_CHECK_FAILED": "critical",
    "SLOW_RESPONSE": "warning",
    "HIGH_ERROR_RATE": "warning",
    "AUTH_FAILURE": "warning",
    "RATE_LIMIT": "warning",
    "CLIENT_ERROR": "info",
}


def utcnow() -> datetime:
    """Naive UTC timestamp (see app.models.utcnow)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _new_public_id() -> str:
    return f"INC-{utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def _channels_for(severity: str) -> list[str]:
    channels = ["slack", "email"]
    if severity == "critical":
        channels.append("call")
    return channels


class MonitorEngine:
    """Background synthetic monitor."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self.running = False
        self.cycles: int = 0
        self.last_cycle_at: datetime | None = None
        self.last_cycle_duration_ms: float = 0.0

    # ------------------------------------------------------------------ loop
    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop(), name="apiguard-monitor")

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _loop(self) -> None:
        await asyncio.sleep(1.5)  # give the app a moment to finish booting
        while self.running:
            started = utcnow()
            try:
                await self.run_cycle()
            except Exception:  # noqa: BLE001 - the monitor must never die
                tb_module.print_exc()
            self.last_cycle_duration_ms = (utcnow() - started).total_seconds() * 1000
            self.last_cycle_at = utcnow()
            await asyncio.sleep(max(2, settings.PROBE_INTERVAL_SECONDS))

    # ----------------------------------------------------------------- probe
    async def run_cycle(self) -> list[dict[str, Any]]:
        """Probe every enabled endpoint once and evaluate the rules."""
        results: list[dict[str, Any]] = []
        timeout = httpx.Timeout(settings.REQUEST_TIMEOUT_SECONDS, connect=3.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            db = SessionLocal()
            try:
                endpoints = db.query(Endpoint).filter(Endpoint.enabled.is_(True)).all()
                eps = [
                    {
                        "id": e.id,
                        "name": e.name,
                        "path": e.path,
                        "method": e.method,
                        "expected_status": e.expected_status,
                        "latency_threshold_ms": e.latency_threshold_ms,
                        "criticality": e.criticality,
                    }
                    for e in endpoints
                ]
            finally:
                db.close()

            for ep in eps:
                result = await self._probe(client, ep)
                results.append(result)
                await run_in_threadpool(self._persist_and_evaluate, ep, result)
            self.cycles += 1

        await run_in_threadpool(self.evaluate_live_traffic)
        await run_in_threadpool(self.sweep_stale_incidents)
        await run_in_threadpool(self._refresh_gauges)
        return results

    async def _probe(self, client: httpx.AsyncClient, ep: dict[str, Any]) -> dict[str, Any]:
        url = f"{settings.SELF_BASE_URL.rstrip('/')}{ep['path']}"
        headers = {"X-Request-ID": f"probe-{uuid.uuid4().hex[:12]}", "User-Agent": "APIGuard-Monitor/1.0"}
        if ep["path"].startswith("/secure-data"):
            headers["X-API-Key"] = sorted(settings.valid_api_keys)[0]

        started = asyncio.get_event_loop().time()
        try:
            resp = await client.request(ep["method"], url, headers=headers)
            latency = (asyncio.get_event_loop().time() - started) * 1000
            ok = resp.status_code == ep["expected_status"]
            return {
                "endpoint_id": ep["id"],
                "ok": ok,
                "status_code": resp.status_code,
                "latency_ms": round(latency, 2),
                "error_type": "none" if ok else ("http_error" if resp.status_code else "connection"),
                "error_message": "" if ok else f"unexpected status {resp.status_code}",
                "request_id": resp.headers.get("x-request-id", headers["X-Request-ID"]),
                "source": "synthetic",
            }
        except httpx.TimeoutException:
            latency = (asyncio.get_event_loop().time() - started) * 1000
            return {
                "endpoint_id": ep["id"],
                "ok": False,
                "status_code": None,
                "latency_ms": round(latency, 2),
                "error_type": "timeout",
                "error_message": f"request exceeded {settings.REQUEST_TIMEOUT_SECONDS}s timeout budget",
                "request_id": headers["X-Request-ID"],
                "source": "synthetic",
            }
        except Exception as exc:  # noqa: BLE001 - connection refused, DNS, ...
            latency = (asyncio.get_event_loop().time() - started) * 1000
            return {
                "endpoint_id": ep["id"],
                "ok": False,
                "status_code": None,
                "latency_ms": round(latency, 2),
                "error_type": "connection",
                "error_message": f"{type(exc).__name__}: {exc}",
                "request_id": headers["X-Request-ID"],
                "source": "synthetic",
            }

    # ------------------------------------------------------- persist + rules
    def _persist_and_evaluate(self, ep: dict[str, Any], result: dict[str, Any]) -> None:
        db = SessionLocal()
        try:
            check = Check(
                endpoint_id=ep["id"],
                checked_at=utcnow(),
                ok=bool(result["ok"]),
                status_code=result["status_code"],
                latency_ms=result["latency_ms"],
                error_type=result["error_type"],
                error_message=result["error_message"],
                request_id=result["request_id"],
                source="synthetic",
            )
            db.add(check)
            db.commit()

            metrics.observe_check(
                ep["path"],
                bool(result["ok"]),
                result["status_code"],
                result["latency_ms"] / 1000.0,
            )
            self.evaluate_endpoint(db, ep, result)
        finally:
            db.close()

    def evaluate_endpoint(self, db: Session, ep: dict[str, Any], result: dict[str, Any]) -> list[Incident]:
        """Apply the alert rules for one probe result and reconcile incidents."""
        window_start = utcnow() - timedelta(minutes=settings.ERROR_RATE_WINDOW_MINUTES)
        recent: list[Check] = (
            db.query(Check)
            .filter(Check.endpoint_id == ep["id"])
            .order_by(Check.id.desc())
            .limit(40)
            .all()
        )
        consecutive_failures = 0
        for c in recent:
            if not c.ok:
                consecutive_failures += 1
            else:
                break
        consecutive_successes = 0
        for c in recent:
            if c.ok:
                consecutive_successes += 1
            else:
                break

        window_checks = [c for c in recent if c.checked_at >= window_start]
        failed_in_window = sum(1 for c in window_checks if not c.ok)
        error_rate = (failed_in_window / len(window_checks) * 100) if window_checks else 0.0

        status = result["status_code"]
        error_type = result["error_type"]
        latency = result["latency_ms"]
        threshold = float(ep.get("latency_threshold_ms") or settings.LATENCY_THRESHOLD_MS)

        fired: list[dict[str, Any]] = []

        def fire(rule_id: str, **extra: Any) -> None:
            fired.append(
                {
                    "rule_id": rule_id,
                    "severity": RULE_SEVERITY.get(rule_id, "warning"),
                    "status_code": status,
                    "latency_ms": latency,
                    "error_type": error_type,
                    "error_message": result["error_message"],
                    "extra": extra,
                }
            )

        # --- rule: explicit 5xx
        if status is not None and 500 <= status < 600:
            fire("SERVER_ERROR")
        # --- rule: timeout / 408 / 504
        if error_type == "timeout" or status in (408, 504):
            fire("TIMEOUT")
        # --- rule: auth
        if status in (401, 403):
            fire("AUTH_FAILURE")
        # --- rule: rate limit
        if status == 429:
            fire("RATE_LIMIT")
        # --- rule: endpoint down (transport error or sustained failures)
        if error_type in ("connection", "dns") or (
            consecutive_failures >= settings.DOWNTIME_CONSECUTIVE_FAILURES and status not in (401, 403, 429)
        ):
            fire("API_DOWN", consecutive_failures=consecutive_failures)
        # --- rule: latency SLO (suppressed when a timeout already fired)
        if latency > threshold and not any(f["rule_id"] == "TIMEOUT" for f in fired):
            fire("SLOW_RESPONSE")
        # --- rule: elevated failure rate
        if error_rate > settings.ERROR_RATE_THRESHOLD_PCT and len(window_checks) >= 3:
            fire("HIGH_ERROR_RATE", error_rate_pct=error_rate, error_rate_threshold=settings.ERROR_RATE_THRESHOLD_PCT)
        # --- rule: health endpoint
        if ep["path"] == "/health" and not result["ok"]:
            fire("HEALTH_CHECK_FAILED")

        incidents: list[Incident] = []
        for f in fired:
            incidents.append(
                self._record_failure(
                    db,
                    endpoint_id=ep["id"],
                    endpoint_path=ep["path"],
                    method=ep["method"],
                    result=result,
                    rule=f,
                )
            )

        # ---- auto-resolve rules that are no longer firing
        if consecutive_successes >= settings.RECOVERY_CONSECUTIVE_SUCCESSES:
            fired_ids = {f["rule_id"] for f in fired}
            open_incidents = (
                db.query(Incident)
                .filter(Incident.endpoint_id == ep["id"], Incident.status.in_(["open", "acknowledged"]))
                .all()
            )
            for inc in open_incidents:
                if inc.rule_id not in fired_ids:
                    self._resolve(db, inc)
        db.commit()
        return incidents

    # ------------------------------------------------------------- lifecycle
    def _record_failure(
        self,
        db: Session,
        *,
        endpoint_id: int | None,
        endpoint_path: str,
        method: str = "GET",
        result: dict[str, Any],
        rule: dict[str, Any],
        source: str = "synthetic",
    ) -> Incident:
        """Create or update an incident for (endpoint, rule) and alert on cooldown."""
        rule_id = rule["rule_id"]
        severity = rule["severity"]
        now = utcnow()

        analysis = rca.analyse(
            rule_id=rule_id,
            status_code=rule.get("status_code"),
            error_type=rule.get("error_type", "none"),
            latency_ms=rule.get("latency_ms"),
            threshold_ms=settings.LATENCY_THRESHOLD_MS,
            path=endpoint_path,
            method=method,
            request_id=result.get("request_id", ""),
            error_message=rule.get("error_message", ""),
            db=db,
            extra=rule.get("extra", {}),
        )
        analysis["evidence"].update(
            {
                "source": source,
                "detection_time_utc": now.isoformat(),
                "rule": rca.RULE_CATALOG.get(rule_id, {}).get("description", ""),
            }
        )

        incident = (
            db.query(Incident)
            .filter(
                Incident.endpoint_id == endpoint_id,
                Incident.rule_id == rule_id,
                Incident.status.in_(["open", "acknowledged"]),
            )
            .order_by(Incident.id.desc())
            .first()
        )

        title = f"{rca.RULE_CATALOG.get(rule_id, {}).get('title', rule_id)} on {endpoint_path}"

        if incident is None:
            incident = Incident(
                public_id=_new_public_id(),
                endpoint_id=endpoint_id,
                endpoint_path=endpoint_path,
                rule_id=rule_id,
                title=title,
                severity=severity,
                status="open",
                category=analysis["category"],
                http_status=rule.get("status_code"),
                latency_ms=rule.get("latency_ms"),
                error_type=rule.get("error_type", "none"),
                root_cause=analysis["root_cause"],
                root_cause_confidence=analysis["root_cause_confidence"],
                probable_causes=analysis["probable_causes"],
                evidence=analysis["evidence"],
                recommended_actions=analysis["recommended_actions"],
                owner_team=analysis["owner_team"],
                detected_at=now,
                last_seen_at=now,
                occurrences=1,
            )
            db.add(incident)
            db.flush()
            alerted = True
        else:
            incident.occurrences += 1
            incident.last_seen_at = now
            incident.severity = severity
            incident.http_status = rule.get("status_code")
            incident.latency_ms = rule.get("latency_ms")
            incident.root_cause = analysis["root_cause"]
            incident.probable_causes = analysis["probable_causes"]
            incident.evidence = analysis["evidence"]
            incident.recommended_actions = analysis["recommended_actions"]
            # Respect the alert cooldown so a flapping endpoint does not spam.
            alerted = self._cooldown_elapsed(db, incident.id)

        db.commit()

        if alerted:
            alerts = dispatch(
                db,
                incident,
                channels=_channels_for(severity),
                note=f"Triggered by rule {rule_id} ({source} detection).",
            )
            for a in alerts:
                metrics.observe_alert(a.channel, a.status)
        return incident

    @staticmethod
    def _cooldown_elapsed(db: Session, incident_id: int) -> bool:
        from app.models import Alert

        last = (
            db.query(Alert)
            .filter(Alert.incident_id == incident_id)
            .order_by(Alert.id.desc())
            .first()
        )
        if not last or not last.created_at:
            return True
        last_ts = last.created_at
        return (utcnow() - last_ts).total_seconds() >= settings.ALERT_COOLDOWN_SECONDS

    @staticmethod
    def _resolve(db: Session, incident: Incident) -> None:
        if incident.status == "resolved":
            return
        incident.status = "resolved"
        incident.resolved_at = utcnow()
        incident.duration_seconds = (incident.resolved_at - incident.detected_at).total_seconds()
        db.commit()

    # --------------------------------------------------------- live traffic
    def evaluate_live_traffic(self, window_seconds: int = 90) -> list[Incident]:
        """Turn real inbound failures (5xx/429/401/timeouts) into incidents."""
        db = SessionLocal()
        try:
            marker = db.get(SettingKV, "live_eval_last_id")
            last_id = int(marker.value) if marker and marker.value.isdigit() else 0
            since = utcnow() - timedelta(seconds=window_seconds)
            logs = (
                db.query(RequestLog)
                .filter(
                    RequestLog.id > last_id,
                    RequestLog.ts >= since,
                    RequestLog.is_error.is_(True),
                    ~RequestLog.request_id.like("seed-%"),  # ignore seeded demo traffic
                )
                .order_by(RequestLog.id.asc())
                .all()
            )
            if not logs:
                return []

            max_id = max(l.id for l in logs)
            incidents: list[Incident] = []
            # One incident per (path, rule) inside the evaluation window.
            grouped: dict[tuple[str, str], list[RequestLog]] = {}
            for log in logs:
                rule_id = self._rule_for_status(log.status_code)
                if not rule_id:
                    continue
                grouped.setdefault((log.path, rule_id), []).append(log)

            for (path, rule_id), items in grouped.items():
                latest = items[-1]
                endpoint = db.query(Endpoint).filter(Endpoint.path == path).first()
                threshold = endpoint.latency_threshold_ms if endpoint else settings.LATENCY_THRESHOLD_MS
                result = {
                    "ok": False,
                    "status_code": latest.status_code,
                    "latency_ms": latest.latency_ms,
                    "error_type": "none",
                    "error_message": f"live traffic failure on {path}",
                    "request_id": latest.request_id,
                }
                rule = {
                    "rule_id": rule_id,
                    "severity": RULE_SEVERITY.get(rule_id, "warning"),
                    "status_code": latest.status_code,
                    "latency_ms": latest.latency_ms,
                    "error_type": "none",
                    "error_message": result["error_message"],
                    "extra": {"occurrences": len(items), "threshold_ms": threshold},
                }
                incidents.append(
                    self._record_failure(
                        db,
                        endpoint_id=endpoint.id if endpoint else None,
                        endpoint_path=path,
                        method=latest.method,
                        result=result,
                        rule=rule,
                        source="live",
                    )
                )

            if marker is None:
                db.add(SettingKV(key="live_eval_last_id", value=str(max_id)))
            else:
                marker.value = str(max_id)
            db.commit()
            return incidents
        finally:
            db.close()

    # ------------------------------------------------- manual / lab results
    def record_manual_result(
        self,
        *,
        path: str,
        method: str = "GET",
        status_code: int | None = None,
        latency_ms: float = 0.0,
        error_type: str = "none",
        error_message: str = "",
        request_id: str = "",
        rule_override: str | None = None,
        source: str = "failure-lab",
    ) -> list[int]:
        """Deterministic detection for an externally observed failure.

        Used by the Failure Lab so every scenario is detected the instant it is
        triggered (no waiting for the next probe cycle).

        Returns the ids of the created/updated incidents (ids are returned
        instead of ORM objects because this runs on its own short-lived
        session).
        """
        db = SessionLocal()
        try:
            endpoint = db.query(Endpoint).filter(Endpoint.path == path).first()
            threshold = endpoint.latency_threshold_ms if endpoint else settings.LATENCY_THRESHOLD_MS

            derived: set[str] = set()
            if status_code is not None and 500 <= status_code < 600:
                derived.add("SERVER_ERROR")
            if error_type == "timeout" or status_code in (408, 504):
                derived.add("TIMEOUT")
            if status_code in (401, 403):
                derived.add("AUTH_FAILURE")
            if status_code == 429:
                derived.add("RATE_LIMIT")
            if error_type in ("connection", "dns"):
                derived.add("API_DOWN")
            if latency_ms > threshold and "TIMEOUT" not in derived:
                derived.add("SLOW_RESPONSE")
            if path == "/health" and status_code != 200:
                derived.add("HEALTH_CHECK_FAILED")
            if not derived:
                derived.add("CLIENT_ERROR")
            if rule_override:
                derived.add(rule_override)
                if rule_override == "HEALTH_CHECK_FAILED":
                    derived.discard("SERVER_ERROR")
                if rule_override in ("TIMEOUT",):
                    derived.discard("SLOW_RESPONSE")

            result = {
                "ok": False,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "error_type": error_type,
                "error_message": error_message,
                "request_id": request_id,
            }
            incidents: list[Incident] = []
            for rule_id in sorted(derived):
                rule = {
                    "rule_id": rule_id,
                    "severity": RULE_SEVERITY.get(rule_id, "warning"),
                    "status_code": status_code,
                    "latency_ms": latency_ms,
                    "error_type": error_type,
                    "error_message": error_message,
                    "extra": {"latency_threshold_ms": threshold, "source": source},
                }
                incidents.append(
                    self._record_failure(
                        db,
                        endpoint_id=endpoint.id if endpoint else None,
                        endpoint_path=path,
                        method=method,
                        result=result,
                        rule=rule,
                        source=source,
                    )
                )
            # Put the override / headline rule first so the UI highlights it.
            if rule_override:
                incidents.sort(key=lambda i: (i.rule_id != rule_override, i.rule_id))
            return [i.id for i in incidents]
        finally:
            db.close()

    @staticmethod
    def _rule_for_status(status_code: int | None) -> str | None:
        if status_code is None:
            return "API_DOWN"
        if 500 <= status_code < 600:
            return "SERVER_ERROR"
        if status_code == 429:
            return "RATE_LIMIT"
        if status_code in (401, 403):
            return "AUTH_FAILURE"
        if status_code in (408, 504):
            return "TIMEOUT"
        return None

    # -------------------------------------------------------- stale sweeper
    def sweep_stale_incidents(self) -> int:
        """Auto-resolve incidents that have not re-occurred.

        A rule that is still failing updates `last_seen_at` on every probe
        cycle, so an incident quiet for longer than STALE_INCIDENT_MINUTES has
        recovered (this also cleans up one-off failures from the Failure Lab).
        """
        db = SessionLocal()
        try:
            cutoff = utcnow() - timedelta(minutes=settings.STALE_INCIDENT_MINUTES)
            stale = (
                db.query(Incident)
                .filter(
                    Incident.status.in_(["open", "acknowledged"]),
                    Incident.last_seen_at < cutoff,
                )
                .all()
            )
            for inc in stale:
                self._resolve(db, inc)
            return len(stale)
        finally:
            db.close()

    # ------------------------------------------------------------- gauges
    def _refresh_gauges(self) -> None:
        db = SessionLocal()
        try:
            rows = (
                db.query(Incident.rule_id, func.count(Incident.id))
                .filter(Incident.status.in_(["open", "acknowledged"]))
                .group_by(Incident.rule_id)
                .all()
            )
            metrics.refresh_incident_gauges({r: c for r, c in rows})
            open_critical = (
                db.query(func.count(Incident.id))
                .filter(Incident.status.in_(["open", "acknowledged"]), Incident.severity == "critical")
                .scalar()
                or 0
            )
            metrics.SERVICE_UP.set(0 if open_critical else 1)
        finally:
            db.close()

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "cycles": self.cycles,
            "interval_seconds": settings.PROBE_INTERVAL_SECONDS,
            "last_cycle_at": self.last_cycle_at.isoformat() if self.last_cycle_at else None,
            "last_cycle_duration_ms": round(self.last_cycle_duration_ms, 2),
        }


engine = MonitorEngine()
