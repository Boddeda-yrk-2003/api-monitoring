"""
Test suite for the APIGuard sample API and monitoring pipeline.

Run with:
    cd backend && pytest -q

`tests/conftest.py` boots a private uvicorn instance (port 8123) with its own
SQLite file and alert outbox, so the suite is hermetic and never touches the
data of a running development server.

The tests exercise:
  * every sample endpoint (success + each failure scenario)
  * the monitoring control plane (summary, timeseries, endpoints, incidents)
  * alert-rule evaluation and the full incident lifecycle
  * root cause classification for auth / timeout / 5xx / 429 / health / downtime
  * Prometheus exposition output
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.core.config import settings  # noqa: E402  (env prepared in conftest)




# --------------------------------------------------------------------- #
# Sample API
# --------------------------------------------------------------------- #
def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["database"] == "connected"
    assert "X-Request-ID" in r.headers
    assert "X-Response-Time" in r.headers


def test_users_and_products(client):
    users = client.get("/users?limit=5")
    assert users.status_code == 200
    assert len(users.json()) == 5

    products = client.get("/products?limit=3")
    assert products.status_code == 200
    assert len(products.json()) == 3


def test_user_not_found_returns_404(client):
    r = client.get("/users/9999")
    assert r.status_code == 404


def test_secure_data_requires_api_key(client):
    assert client.get("/secure-data").status_code == 401
    assert client.get("/secure-data", headers={"X-API-Key": "wrong-key"}).status_code == 403
    ok = client.get("/secure-data", headers={"X-API-Key": "demo-api-key-123"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "ok"


def test_simulate_error_returns_500_and_is_captured(client, db):
    r = client.get("/simulate-error")
    assert r.status_code == 500
    assert r.json()["exception_type"] == "RuntimeError"

    errors = client.get("/monitor/errors?limit=5").json()
    assert errors, "exception must be captured for root cause analysis"
    assert errors[0]["exception_type"] == "RuntimeError"
    assert "Traceback" in errors[0]["traceback"]


def test_simulate_timeout_is_slow(client):
    r = client.get("/simulate-timeout?seconds=1")
    assert r.status_code == 200
    assert r.json()["slept_seconds"] == 1


def test_simulate_rate_limit(client):
    codes = [client.get("/simulate-rate-limit").status_code for _ in range(settings.RATE_LIMIT_MAX_REQUESTS + 2)]
    assert 429 in codes
    assert codes[-1] == 429


def test_simulate_auth_error(client):
    assert client.get("/simulate-auth-error").status_code == 401


# --------------------------------------------------------------------- #
# Monitoring control plane
# --------------------------------------------------------------------- #
def test_summary_shape(client):
    data = client.get("/monitor/summary?window=1h").json()
    for key in ("uptime_pct", "avg_latency_ms", "total_requests", "failed_requests", "open_incidents"):
        assert key in data


def test_timeseries_and_endpoints(client):
    assert isinstance(client.get("/monitor/timeseries?window=1h").json(), list)
    endpoints = client.get("/monitor/endpoints?window=1h").json()
    assert endpoints
    assert {e["path"] for e in endpoints} >= {"/health", "/users", "/products"}


def test_probe_cycle_records_checks(client):
    before = client.get("/monitor/summary?window=1h").json()["total_checks"]
    client.post("/monitor/probe/now")
    after = client.get("/monitor/summary?window=1h").json()["total_checks"]
    assert after > before


def test_prometheus_metrics_exposed(client):
    text = client.get("/metrics").text
    assert "apiguard_http_requests_total" in text
    assert "apiguard_endpoint_up" in text


# --------------------------------------------------------------------- #
# Failure scenarios -> detection -> RCA -> alerting
# --------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "scenario,expected_rule,expected_category",
    [
        ("auth", "AUTH_FAILURE", "authentication"),
        ("server_error", "SERVER_ERROR", "server_error"),
        ("rate_limit", "RATE_LIMIT", "rate_limit"),
        ("slow_response", "SLOW_RESPONSE", "latency"),
        ("health_failure", "HEALTH_CHECK_FAILED", "health"),
        ("downtime", "API_DOWN", "availability"),
    ],
)
def test_scenario_detection(client, scenario, expected_rule, expected_category):
    result = client.post(f"/monitor/simulate/{scenario}").json()
    assert result["detected"] is True, result
    assert result["incident"]["rule_id"] == expected_rule
    assert result["incident"]["category"] == expected_category
    assert result["incident"]["root_cause"]
    assert result["incident"]["recommended_actions"]
    assert result["alerts"], "at least one notification must be dispatched"

    channels = {a["channel"] for a in result["alerts"]}
    assert {"slack", "email"} <= channels


def test_server_error_captures_traceback_evidence(client):
    result = client.post("/monitor/simulate/server_error").json()
    evidence = result["incident"]["evidence"]
    assert evidence["exception_type"] == "RuntimeError"
    assert "Traceback" in evidence.get("traceback", "")


def test_incident_lifecycle_and_dedupe(client):
    first = client.post("/monitor/simulate/auth").json()
    incident_id = first["incident"]["id"]
    occurrences = first["incident"]["occurrences"]

    second = client.post("/monitor/simulate/auth").json()
    assert second["incident"]["id"] == incident_id, "same rule+endpoint must reuse the open incident"
    assert second["incident"]["occurrences"] >= occurrences

    ack = client.post(f"/monitor/incidents/{incident_id}/acknowledge").json()
    assert ack["status"] == "acknowledged"

    resolved = client.post(f"/monitor/incidents/{incident_id}/resolve").json()
    assert resolved["status"] == "resolved"
    assert resolved["duration_seconds"] is not None


def test_notification_channel_test(client):
    results = client.post("/monitor/notifications/test?channels=slack,email,call").json()
    assert len(results) == 3
    assert {r["channel"] for r in results} == {"slack", "email", "call"}
    assert all(r["payload"] for r in results)


def test_settings_update(client):
    before = client.get("/monitor/settings").json()
    updated = client.put("/monitor/settings", json={"latency_threshold_ms": 1500}).json()
    assert updated["latency_threshold_ms"] == 1500
    client.put("/monitor/settings", json={"latency_threshold_ms": before["latency_threshold_ms"]})
