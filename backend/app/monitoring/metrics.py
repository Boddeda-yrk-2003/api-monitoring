"""
Prometheus instrumentation.

Exposed on GET /metrics in the standard text format so the same service can be
scraped by Prometheus and visualised in Grafana (see docs/GRAFANA.md).
"""
from __future__ import annotations

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram

# A private registry keeps `uvicorn`/`python` default collectors out of the way
# while still allowing them to be added later via process/platform collectors.
registry = CollectorRegistry()

REQUESTS_TOTAL = Counter(
    "apiguard_http_requests_total",
    "Total inbound HTTP requests handled by the sample API",
    ["method", "path", "status_code"],
    registry=registry,
)

REQUEST_LATENCY = Histogram(
    "apiguard_http_request_duration_seconds",
    "Inbound request latency in seconds",
    ["method", "path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 15.0, float("inf")),
    registry=registry,
)

CHECK_TOTAL = Counter(
    "apiguard_monitor_checks_total",
    "Synthetic monitor checks executed",
    ["endpoint", "outcome", "status_code"],
    registry=registry,
)

CHECK_LATENCY = Histogram(
    "apiguard_monitor_check_duration_seconds",
    "Synthetic probe duration in seconds",
    ["endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 15.0, float("inf")),
    registry=registry,
)

ENDPOINT_UP = Gauge(
    "apiguard_endpoint_up",
    "1 when the endpoint is healthy, 0 when it is failing",
    ["endpoint"],
    registry=registry,
)

ENDPOINT_LATENCY = Gauge(
    "apiguard_endpoint_latency_seconds",
    "Last measured probe latency in seconds",
    ["endpoint"],
    registry=registry,
)

INCIDENTS_OPEN = Gauge(
    "apiguard_incidents_open",
    "Currently open incidents",
    ["rule"],
    registry=registry,
)

ALERTS_TOTAL = Counter(
    "apiguard_alerts_delivered_total",
    "Alert delivery attempts by channel and status",
    ["channel", "status"],
    registry=registry,
)

SERVICE_UP = Gauge(
    "apiguard_service_up",
    "Overall service availability (1 = healthy)",
    registry=registry,
)


def observe_request(method: str, path: str, status_code: int, duration_s: float) -> None:
    REQUESTS_TOTAL.labels(method, path, str(status_code)).inc()
    REQUEST_LATENCY.labels(method, path).observe(duration_s)


def observe_check(endpoint: str, ok: bool, status_code: int | None, duration_s: float) -> None:
    CHECK_TOTAL.labels(endpoint, "success" if ok else "failure", str(status_code or 0)).inc()
    CHECK_LATENCY.labels(endpoint).observe(duration_s)
    ENDPOINT_UP.labels(endpoint).set(1 if ok else 0)
    ENDPOINT_LATENCY.labels(endpoint).set(duration_s)


def observe_alert(channel: str, status: str) -> None:
    ALERTS_TOTAL.labels(channel, status).inc()


def refresh_incident_gauges(counts: dict[str, int]) -> None:
    for rule, count in counts.items():
        INCIDENTS_OPEN.labels(rule).set(count)
