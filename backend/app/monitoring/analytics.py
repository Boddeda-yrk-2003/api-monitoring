"""
Aggregations that power the dashboard.

Everything is expressed as a windowed query over the `checks` (synthetic
monitor) and `request_logs` (real traffic) tables.

NOTE: the time-bucket expression below uses SQLite's `strftime('%s', ...)`.
The project targets SQLite (see docs/DATABASE_SCHEMA.md); on PostgreSQL swap it
for `date_trunc('minute', checked_at)`.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Integer, cast, func
from sqlalchemy.orm import Session

from app.models import Alert, Check, Endpoint, Incident, RequestLog

WINDOWS: dict[str, tuple[timedelta, int]] = {
    # label: (window length, bucket size in minutes)
    "15m": (timedelta(minutes=15), 1),
    "1h": (timedelta(hours=1), 2),
    "6h": (timedelta(hours=6), 10),
    "24h": (timedelta(hours=24), 30),
    "7d": (timedelta(days=7), 360),
    "30d": (timedelta(days=30), 1440),
}


def now_utc() -> datetime:
    return datetime.now(tz=__import__("datetime").timezone.utc).replace(tzinfo=None)


def resolve_window(window: str) -> tuple[datetime, int]:
    length, bucket = WINDOWS.get(window, WINDOWS["24h"])
    return now_utc() - length, bucket


def settings_error_rate_floor() -> float:
    """Error-rate (percent) above which the service is reported as degraded."""
    from app.core.config import settings

    return float(settings.ERROR_RATE_THRESHOLD_PCT)


def _pct(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return float(ordered[k])


# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #
def summary(db: Session, window: str = "24h") -> dict[str, Any]:
    start, _ = resolve_window(window)

    total_checks, ok_checks, avg_latency, max_latency = (
        db.query(
            func.count(Check.id),
            func.sum(cast(Check.ok, Integer)),
            func.avg(Check.latency_ms),
            func.max(Check.latency_ms),
        )
        .filter(Check.checked_at >= start)
        .first()
    )
    total_checks = total_checks or 0
    ok_checks = ok_checks or 0
    uptime = (ok_checks / total_checks * 100) if total_checks else 100.0

    latencies = [float(r[0]) for r in db.query(Check.latency_ms).filter(Check.checked_at >= start).all()]
    p95 = _pct(latencies, 95)

    total_requests = db.query(func.count(RequestLog.id)).filter(RequestLog.ts >= start).scalar() or 0
    failed_requests = (
        db.query(func.count(RequestLog.id))
        .filter(RequestLog.ts >= start, RequestLog.is_error.is_(True))
        .scalar()
        or 0
    )

    open_incidents = (
        db.query(func.count(Incident.id)).filter(Incident.status.in_(["open", "acknowledged"])).scalar() or 0
    )
    critical_incidents = (
        db.query(func.count(Incident.id))
        .filter(Incident.status.in_(["open", "acknowledged"]), Incident.severity == "critical")
        .scalar()
        or 0
    )
    alerts_24h = (
        db.query(func.count(Alert.id)).filter(Alert.created_at >= now_utc() - timedelta(hours=24)).scalar() or 0
    )

    endpoints = db.query(Endpoint).filter(Endpoint.enabled.is_(True)).all()
    stats = endpoint_stats(db, window)
    up = sum(1 for s in stats if s["status"] == "healthy" and s["enabled"])
    degraded = sum(1 for s in stats if s["status"] == "degraded")
    down = sum(1 for s in stats if s["status"] == "down")

    error_rate = (failed_requests / total_requests * 100) if total_requests else 0.0
    check_error_rate = ((total_checks - ok_checks) / total_checks * 100) if total_checks else 0.0
    if critical_incidents or down:
        status = "critical"
    elif degraded or error_rate > settings_error_rate_floor():
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "uptime_pct": round(uptime, 3),
        "avg_latency_ms": round(float(avg_latency or 0.0), 2),
        "p95_latency_ms": round(p95, 2),
        "max_latency_ms": round(float(max_latency or 0.0), 2),
        "total_requests": int(total_requests),
        "failed_requests": int(failed_requests),
        "error_rate_pct": round(error_rate, 2),
        "check_error_rate_pct": round(check_error_rate, 2),
        "total_checks": int(total_checks),
        "open_incidents": int(open_incidents),
        "critical_incidents": int(critical_incidents),
        "alerts_last_24h": int(alerts_24h),
        "endpoints_monitored": len(endpoints),
        "endpoints_up": up,
        "endpoints_down": down,
        "endpoints_degraded": degraded,
        "window": window,
        "generated_at": now_utc(),
        "monitor_running": True,
    }


# --------------------------------------------------------------------------- #
# Time series
# --------------------------------------------------------------------------- #
def timeseries(db: Session, window: str = "24h", endpoint_id: int | None = None) -> list[dict[str, Any]]:
    start, bucket_minutes = resolve_window(window)
    bucket_seconds = bucket_minutes * 60

    q = db.query(
        (cast(func.strftime("%s", Check.checked_at), Integer) / bucket_seconds).label("bucket"),
        func.count(Check.id),
        func.sum(cast(Check.ok, Integer)),
        func.avg(Check.latency_ms),
        func.max(Check.latency_ms),
    ).filter(Check.checked_at >= start)
    if endpoint_id:
        q = q.filter(Check.endpoint_id == endpoint_id)
    rows = q.group_by("bucket").order_by("bucket").all()

    points: dict[int, dict[str, Any]] = {}
    for bucket, total, ok, avg, mx in rows:
        ts = datetime.utcfromtimestamp(int(bucket) * bucket_seconds)
        points[int(bucket)] = {
            "bucket": ts.strftime("%Y-%m-%dT%H:%M:00Z"),
            "total": int(total or 0),
            "success": int(ok or 0),
            "failed": int((total or 0) - (ok or 0)),
            "avg_latency_ms": round(float(avg or 0.0), 2),
            "max_latency_ms": round(float(mx or 0.0), 2),
            "error_rate_pct": round((((total or 0) - (ok or 0)) / (total or 1)) * 100, 2),
        }

    # p95 per bucket (percentiles are not supported by SQLite aggregates)
    lat_rows = (
        db.query(
            (cast(func.strftime("%s", Check.checked_at), Integer) / bucket_seconds).label("bucket"),
            Check.latency_ms,
        )
        .filter(Check.checked_at >= start)
        .all()
    )
    grouped: dict[int, list[float]] = {}
    for bucket, latency in lat_rows:
        grouped.setdefault(int(bucket), []).append(float(latency or 0.0))
    for bucket, values in grouped.items():
        if bucket in points:
            points[bucket]["p95_latency_ms"] = round(_pct(values, 95), 2)

    return [points[k] for k in sorted(points)]


# --------------------------------------------------------------------------- #
# Per endpoint
# --------------------------------------------------------------------------- #
def endpoint_stats(db: Session, window: str = "24h") -> list[dict[str, Any]]:
    start, _ = resolve_window(window)
    out: list[dict[str, Any]] = []
    endpoints = db.query(Endpoint).order_by(Endpoint.group_name, Endpoint.name).all()

    for ep in endpoints:
        agg = (
            db.query(
                func.count(Check.id),
                func.sum(cast(Check.ok, Integer)),
                func.avg(Check.latency_ms),
                func.max(Check.latency_ms),
            )
            .filter(Check.endpoint_id == ep.id, Check.checked_at >= start)
            .first()
        )
        total = int(agg[0] or 0)
        ok = int(agg[1] or 0)
        latencies = [
            float(r[0])
            for r in db.query(Check.latency_ms)
            .filter(Check.endpoint_id == ep.id, Check.checked_at >= start)
            .all()
        ]
        last_check = (
            db.query(Check).filter(Check.endpoint_id == ep.id).order_by(Check.id.desc()).first()
        )
        spark_rows = (
            db.query(Check.latency_ms, Check.ok)
            .filter(Check.endpoint_id == ep.id)
            .order_by(Check.id.desc())
            .limit(30)
            .all()
        )
        sparkline = [round(float(r[0]), 2) for r in reversed(spark_rows)]
        open_incidents = (
            db.query(func.count(Incident.id))
            .filter(Incident.endpoint_id == ep.id, Incident.status.in_(["open", "acknowledged"]))
            .scalar()
            or 0
        )

        uptime = (ok / total * 100) if total else (100.0 if not ep.enabled else 0.0)
        error_rate = ((total - ok) / total * 100) if total else 0.0

        # Current health is derived from the most recent probes (a resolved
        # incident in the window must not keep the endpoint marked degraded).
        recent = (
            db.query(Check.ok, Check.latency_ms)
            .filter(Check.endpoint_id == ep.id)
            .order_by(Check.id.desc())
            .limit(5)
            .all()
        )
        recent_failures = sum(1 for r in recent if not r[0])

        if not ep.enabled:
            status = "paused"
        elif not recent:
            status = "unknown"
        elif recent_failures == len(recent):
            status = "down"
        elif recent_failures >= 2:
            status = "degraded"
        elif last_check and last_check.latency_ms > ep.latency_threshold_ms:
            status = "degraded"
        else:
            status = "healthy"

        out.append(
            {
                "id": ep.id,
                "name": ep.name,
                "path": ep.path,
                "method": ep.method,
                "description": ep.description,
                "group_name": ep.group_name,
                "criticality": ep.criticality,
                "enabled": ep.enabled,
                "expected_status": ep.expected_status,
                "latency_threshold_ms": ep.latency_threshold_ms,
                "status": status,
                "uptime_pct": round(uptime, 3),
                "avg_latency_ms": round(float(agg[2] or 0.0), 2),
                "p95_latency_ms": round(_pct(latencies, 95), 2),
                "max_latency_ms": round(float(agg[3] or 0.0), 2),
                "total_checks": total,
                "failed_checks": int(total - ok),
                "error_rate_pct": round(error_rate, 2),
                "last_status_code": last_check.status_code if last_check else None,
                "last_checked_at": last_check.checked_at if last_check else None,
                "last_error": (last_check.error_message or "") if last_check else "",
                "open_incidents": int(open_incidents),
                "sparkline": sparkline,
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Traffic + status distribution
# --------------------------------------------------------------------------- #
def status_breakdown(db: Session, window: str = "24h") -> list[dict[str, Any]]:
    start, _ = resolve_window(window)
    rows = (
        db.query(RequestLog.status_code, func.count(RequestLog.id))
        .filter(RequestLog.ts >= start)
        .group_by(RequestLog.status_code)
        .order_by(func.count(RequestLog.id).desc())
        .all()
    )
    labels = {200: "2xx OK", 401: "401 Unauthorized", 404: "404 Not Found", 429: "429 Rate Limited", 500: "500 Server Error"}
    out = []
    for code, count in rows:
        label = labels.get(code, f"{code // 100}xx")
        out.append({"status_code": code, "count": int(count), "label": label})
    return out


def traffic_by_path(db: Session, window: str = "24h") -> list[dict[str, Any]]:
    start, _ = resolve_window(window)
    rows = (
        db.query(
            RequestLog.path,
            func.count(RequestLog.id),
            func.avg(RequestLog.latency_ms),
            func.sum(cast(RequestLog.is_error, Integer)),
        )
        .filter(RequestLog.ts >= start)
        .group_by(RequestLog.path)
        .order_by(func.count(RequestLog.id).desc())
        .limit(12)
        .all()
    )
    return [
        {
            "path": p,
            "requests": int(c or 0),
            "avg_latency_ms": round(float(a or 0.0), 2),
            "errors": int(e or 0),
        }
        for p, c, a, e in rows
    ]


def uptime_timeline(db: Session, endpoint_id: int, hours: int = 24, slot_minutes: int = 30) -> list[dict[str, Any]]:
    """Classic uptime strip: one coloured slot per time bucket."""
    start = now_utc() - timedelta(hours=hours)
    bucket_seconds = slot_minutes * 60
    rows = (
        db.query(
            (cast(func.strftime("%s", Check.checked_at), Integer) / bucket_seconds).label("bucket"),
            func.count(Check.id),
            func.sum(cast(Check.ok, Integer)),
        )
        .filter(Check.endpoint_id == endpoint_id, Check.checked_at >= start)
        .group_by("bucket")
        .order_by("bucket")
        .all()
    )
    out = []
    for bucket, total, ok in rows:
        total, ok = int(total or 0), int(ok or 0)
        ratio = (ok / total) if total else 1.0
        if ratio == 1.0:
            state = "up"
        elif ratio >= 0.5:
            state = "degraded"
        else:
            state = "down"
        out.append(
            {
                "bucket": datetime.utcfromtimestamp(int(bucket) * bucket_seconds).strftime("%Y-%m-%dT%H:%M:00Z"),
                "state": state,
                "uptime_pct": round(ratio * 100, 1),
                "checks": total,
            }
        )
    return out
