"""
Root Cause Analysis (RCA) engine.

Maps an observed failure (HTTP status / exception / latency / transport error)
onto a structured diagnosis: category, most probable root cause, supporting
evidence, and remediation steps. The engine is rule-based and explainable -
every field it returns is derived from a documented rule so an on-call engineer
can trust (and override) it.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import ErrorLog

# --------------------------------------------------------------------------- #
# Rule catalogue - each rule id maps to a human readable detection contract
# --------------------------------------------------------------------------- #
RULE_CATALOG: dict[str, dict[str, str]] = {
    "API_DOWN": {
        "title": "API endpoint unavailable",
        "description": "Consecutive synthetic probes failed (transport error or non-2xx).",
        "owner": "Platform / SRE",
    },
    "SLOW_RESPONSE": {
        "title": "Response time above SLO",
        "description": "Response time exceeded the configured latency threshold.",
        "owner": "Backend Engineering",
    },
    "SERVER_ERROR": {
        "title": "HTTP 5xx server error",
        "description": "The API returned a 5xx status code (unhandled server exception).",
        "owner": "Backend Engineering",
    },
    "HIGH_ERROR_RATE": {
        "title": "Elevated failure rate",
        "description": "Failure rate over the rolling window exceeded the threshold.",
        "owner": "Backend Engineering",
    },
    "HEALTH_CHECK_FAILED": {
        "title": "Service health check failed",
        "description": "/health did not report a healthy status.",
        "owner": "Platform / SRE",
    },
    "AUTH_FAILURE": {
        "title": "Authentication / authorization failure",
        "description": "Request rejected because credentials were missing, malformed or expired.",
        "owner": "Security / Identity",
    },
    "RATE_LIMIT": {
        "title": "Rate limit exceeded (HTTP 429)",
        "description": "Client or upstream exceeded the configured request quota.",
        "owner": "API Platform",
    },
    "CLIENT_ERROR": {
        "title": "HTTP 4xx client error",
        "description": "Request was rejected due to a client-side problem.",
        "owner": "API Consumers / Backend Engineering",
    },
    "TIMEOUT": {
        "title": "Request timeout",
        "description": "Request exceeded the timeout budget and was aborted.",
        "owner": "Backend Engineering",
    },
}


def _traceback_signature(tb: str) -> str:
    """Return the last (most specific) frames of a traceback."""
    lines = [ln.strip() for ln in (tb or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    tail = [ln for ln in lines if ln.startswith("File ")]
    return " | ".join(tail[-3:]) or lines[-1]


def _lookup_error_log(db: Session | None, request_id: str, path: str | None = None) -> ErrorLog | None:
    if not db:
        return None
    q = db.query(ErrorLog)
    if request_id:
        err = q.filter(ErrorLog.request_id == request_id).order_by(ErrorLog.id.desc()).first()
        if err:
            return err
    if path:
        return q.filter(ErrorLog.path == path).order_by(ErrorLog.id.desc()).first()
    return None


def analyse(
    *,
    rule_id: str,
    status_code: int | None = None,
    error_type: str = "none",
    latency_ms: float | None = None,
    threshold_ms: float = 3000.0,
    path: str = "",
    method: str = "GET",
    request_id: str = "",
    error_message: str = "",
    db: Session | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce a structured root-cause analysis for one observed failure."""
    extra = extra or {}
    code = status_code
    err_log = _lookup_error_log(db, request_id, path)

    category, confidence = "availability", "medium"
    root_cause = ""
    probable: list[str] = []
    actions: list[str] = []
    owner = RULE_CATALOG.get(rule_id, {}).get("owner", "Backend Engineering")
    evidence: dict[str, Any] = {
        "http_status": code,
        "error_type": error_type,
        "latency_ms": round(latency_ms or 0.0, 2),
        "latency_threshold_ms": threshold_ms,
        "path": path,
        "method": method,
        "request_id": request_id,
        "transport_error": error_message or "",
    }

    # ---------------------------------------------------- rule: health check
    # (must be evaluated before the generic 5xx branch: /health reports 503)
    if rule_id == "HEALTH_CHECK_FAILED":
        category = "health"
        confidence = "high"
        root_cause = (
            f"GET /health returned HTTP {code} - the service reported itself unhealthy because a "
            "readiness dependency failed its probe."
        )
        probable = [
            "Database connection pool exhausted or the database is unreachable",
            "A required downstream dependency is degraded",
            "Disk / memory pressure on the host",
        ]
        actions = [
            "Inspect the /health dependency breakdown and the failing component's metrics",
            "Check database connectivity and connection-pool saturation",
            "Fail over to the replica or restart the degraded dependency",
        ]

    # ------------------------------------------------------------ rule: 5xx
    elif rule_id == "SERVER_ERROR" or (code is not None and 500 <= code < 600):
        category = "server_error"
        confidence = "high" if err_log else "medium"
        exc_type = err_log.exception_type if err_log else "Unknown"
        exc_msg = err_log.exception_message if err_log else (error_message or "no captured exception")
        root_cause = (
            f"Unhandled {exc_type} raised while serving {method} {path}: {exc_msg}"
        )
        probable = [
            "Unhandled exception in route handler or a downstream dependency call",
            "Invalid assumption about input data (None / missing key / type mismatch)",
            "Downstream service or database returned an error that was not caught",
            "Recent deployment introduced a regression (check last deploy diff)",
        ]
        actions = [
            f"Inspect captured stack trace for request_id={request_id or 'n/a'} "
            "(Dashboard -> Incidents -> Evidence)",
            "Reproduce with the same payload in staging and add a regression test",
            "Add explicit exception handling + structured logging around the failing call",
            "Roll back the last release if the error started immediately after a deploy",
        ]
        if err_log:
            evidence.update(
                {
                    "exception_type": err_log.exception_type,
                    "exception_message": err_log.exception_message,
                    "traceback": err_log.traceback,
                    "failing_frames": _traceback_signature(err_log.traceback),
                    "captured_at": err_log.ts.isoformat(),
                }
            )
        else:
            evidence["note"] = "No server-side exception captured (error raised before handler or in proxy)."

    # -------------------------------------------------------- rule: timeouts
    elif rule_id == "TIMEOUT" or error_type == "timeout" or code in (408, 504):
        category = "timeout"
        confidence = "high"
        root_cause = (
            f"{method} {path} exceeded the {threshold_ms:.0f} ms timeout budget "
            f"(observed {latency_ms or 0:.0f} ms) and the connection was aborted."
        )
        probable = [
            "Slow downstream dependency (database query, third-party API, cache miss storm)",
            "Blocking I/O inside the request path (sync call in async handler)",
            "Resource saturation - CPU throttling, connection-pool exhaustion, GC pause",
            "Network latency / packet loss between the monitor and the service",
        ]
        actions = [
            "Check database slow-query log and add the missing index / query cache",
            "Move blocking work to a background task or add an async client",
            "Add or tighten upstream timeouts + circuit breaker so callers fail fast",
            "Scale the service horizontally or raise the worker/connection pool size",
        ]
        evidence["timeout_budget_ms"] = threshold_ms * (extra.get("timeout_multiplier", 2.0))

    # --------------------------------------------------------- rule: latency
    elif rule_id == "SLOW_RESPONSE":
        category = "latency"
        confidence = "high"
        root_cause = (
            f"{method} {path} responded in {latency_ms or 0:.0f} ms which is above the "
            f"{threshold_ms:.0f} ms latency SLO."
        )
        probable = [
            "Increased payload size or N+1 query pattern in the handler",
            "Cold cache / cache eviction causing expensive recomputation",
            "Competing load on the host (noisy neighbour, batch job, backup)",
        ]
        actions = [
            "Profile the handler and optimise the dominant query / serialisation cost",
            "Add response caching or pagination for large payloads",
            "Review autoscaling policy and recent traffic growth",
        ]

    # --------------------------------------------------- rule: auth failures
    elif rule_id == "AUTH_FAILURE" or code in (401, 403):
        category = "authentication"
        confidence = "high"
        root_cause = (
            f"{method} {path} rejected the request with HTTP {code}: the API key / token was "
            "missing, malformed, expired or lacks the required scope."
        )
        probable = [
            "Caller omitted the X-API-Key header or sent it in the wrong format",
            "API key was rotated or revoked but the client still uses the old value",
            "Clock skew causing an expired JWT (check exp claim vs server time)",
            "Insufficient scope / role for the requested resource (403)",
        ]
        actions = [
            "Verify the X-API-Key header value against the key store",
            "Check key expiry & rotation schedule; re-issue and redeploy the credential",
            "Confirm the monitoring job's secret store is in sync after rotation",
            "Add a pre-flight credential check to the synthetic monitor",
        ]
        evidence["expected_header"] = "X-API-Key"

    # ------------------------------------------------------ rule: rate limit
    elif rule_id == "RATE_LIMIT" or code == 429:
        category = "rate_limit"
        confidence = "high"
        root_cause = (
            f"{method} {path} returned HTTP 429: the caller exceeded the configured request "
            "quota for the current window."
        )
        probable = [
            "Client or monitor is sending more requests than the quota allows",
            "Retry storm after a previous failure (no exponential backoff / jitter)",
            "Quota is shared across services and another consumer consumed the budget",
        ]
        actions = [
            "Honour the Retry-After header and apply exponential backoff with jitter",
            "Reduce synthetic probe frequency or raise the endpoint quota",
            "Introduce per-consumer quotas so one client cannot starve the others",
        ]
        evidence["retry_after_hint"] = "Retry-After: 60"

    # ------------------------------------------------------ rule: api down
    elif rule_id == "API_DOWN" or error_type in ("connection", "dns"):
        category = "availability"
        confidence = "high"
        root_cause = (
            f"{method} {path} is unreachable - {error_message or 'connection refused'}. "
            "The service process is not accepting connections."
        )
        probable = [
            "Application process crashed or is restarting (OOM / panic / failed healthcheck)",
            "Service is not bound to the expected host/port or the port is firewalled",
            "Reverse proxy / ingress is misrouting after a config reload",
            "Host or container is down",
        ]
        actions = [
            "Check process liveness, restart count and container logs",
            "Verify the listening port and ingress/route configuration",
            "Restart the service and confirm /health returns 200",
            "Review recent deployments and infrastructure events",
        ]

    # ------------------------------------------------------ rule: error rate
    elif rule_id == "HIGH_ERROR_RATE":
        category = "error_rate"
        confidence = "medium"
        observed = extra.get("error_rate_pct", 0.0)
        threshold = extra.get("error_rate_threshold", 5.0)
        root_cause = (
            f"Failure rate for {method} {path} is {observed:.1f}% over the rolling window, "
            f"above the {threshold:.1f}% threshold - this is a sustained degradation, "
            "not a single request failure."
        )
        probable = [
            "A dependency is intermittently failing (partial outage / brownout)",
            "Bad deploy affecting a subset of traffic (canary or region)",
            "Load-induced failures: timeouts and 5xx rise together with traffic",
        ]
        actions = [
            "Correlate the failing window with the deploy and dependency dashboards",
            "Compare error rate per status code to isolate the dominant failure mode",
            "Consider pausing the rollout / scaling out while investigating",
        ]
        evidence["error_rate_pct"] = round(float(observed), 2)
        evidence["error_rate_threshold_pct"] = float(threshold)

    # -------------------------------------------------------- rule: 4xx misc
    elif code is not None and 400 <= code < 500:
        category = "client_error"
        confidence = "medium"
        root_cause = f"{method} {path} returned HTTP {code} - the request was rejected as malformed or not found."
        probable = [
            "Client sent an invalid path parameter or payload",
            "Resource no longer exists (deleted / wrong id)",
            "Contract drift between client and server after an API change",
        ]
        actions = [
            "Validate request parameters against the OpenAPI contract",
            "Return a clearer 4xx with a machine-readable error code",
            "Add contract tests to catch client/server drift in CI",
        ]

    else:
        root_cause = root_cause or (
            f"{method} {path} failed (status={code}, error_type={error_type})."
        )
        probable = probable or ["Unknown - inspect the captured evidence and recent changes"]
        actions = actions or ["Open the incident and attach the captured request id for triage"]

    # Attach any captured exception as supporting evidence for other categories
    if err_log and "exception_type" not in evidence:
        evidence.update(
            {
                "exception_type": err_log.exception_type,
                "exception_message": err_log.exception_message,
                "captured_at": err_log.ts.isoformat(),
            }
        )

    return {
        "category": category,
        "root_cause": root_cause,
        "root_cause_confidence": confidence,
        "probable_causes": probable,
        "evidence": evidence,
        "recommended_actions": actions,
        "owner_team": owner,
        "rule_title": RULE_CATALOG.get(rule_id, {}).get("title", rule_id),
    }


def sanitize(text: str) -> str:
    """Strip ANSI/control characters before persisting log evidence."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text or "")
