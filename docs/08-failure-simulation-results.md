# Failure Simulation & Root Cause Analysis — Test Results

| Field | Value |
|---|---|
| Target | `http://localhost:8000` (backend) · `http://localhost:5173` (dashboard) |
| Runner | `backend/scripts/simulate_failures.py` |
| Executed | 2026-11-01T17:50:28Z |
| Result | **7 / 7 scenarios detected** |
| Artefacts | `backend/data/failure-test-results.json`, `failure-test-results.csv`, `backend/data/alert-outbox/alerts-<date>.jsonl` |

## 1. Summary matrix

| # | Scenario | Endpoint | HTTP | Latency | Rule fired | Severity | Detected | Detection time | Incident | Alerts |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Invalid API authentication | `/secure-data` | **401** | 3 ms | `AUTH_FAILURE` | warning | ✅ | 9 ms | `INC-20261101-5D8FD7` | Email, Slack |
| 2 | API timeout | `/simulate-timeout?seconds=12` | **no response** | 8009 ms | `TIMEOUT` | critical | ✅ | 7 ms | `INC-20261101-FBB3D9` | Call, Email, Slack |
| 3 | Server error (HTTP 500) | `/simulate-error` | **500** | 5 ms | `SERVER_ERROR` | critical | ✅ | 6 ms | `INC-20261101-98052D` | Call, Email, Slack |
| 4 | Rate limit exceeded (HTTP 429) | `/simulate-rate-limit` | **429** | 2 ms | `RATE_LIMIT` | warning | ✅ | 6 ms | `INC-20261101-B06041` | Email, Slack |
| 5 | Latency SLO breach (> 3s) | `/simulate-timeout?seconds=3.5` | **200** | 3504 ms | `SLOW_RESPONSE` | warning | ✅ | 6 ms | `INC-20261101-0EFEE2` | Email, Slack |
| 6 | Service health check failure | `/health?degraded=true` | **503** | 4 ms | `HEALTH_CHECK_FAILED` | critical | ✅ | 6 ms | `INC-20261101-077933` | Call, Email, Slack |
| 7 | API downtime (connection refused) | `http://127.0.0.1:9/health` | **no response** | 8 ms | `API_DOWN` | critical | ✅ | 8 ms | `INC-20261101-3EE8EC` | Call, Email, Slack |

**Detection latency (failure → incident with RCA → notifications dispatched): 6–9 ms** (the probe loop adds at most `PROBE_INTERVAL_SECONDS` for failures that are not triggered through the Failure Lab).

All channels are reported as `simulated` because no webhook/SMTP/Twilio credentials are configured in the demo environment — payloads are fully rendered and stored (see the *Notification proof* section).

## 2. Scenario 1 — Invalid API authentication

**Trigger**: `GET /secure-data` without the `X-API-Key` header.

| Item | Value |
|---|---|
| Observed | `HTTP 401` in 3 ms |
| Rule | `AUTH_FAILURE` (warning) |
| Category | `authentication` |
| Root cause | GET /secure-data rejected the request with HTTP 401: the API key / token was missing, malformed, expired or lacks the required scope. |
| Owner | Security / Identity |
| Confidence | high |
| Alerts | email:simulated, slack:simulated |
| Incident | `INC-20261101-5D8FD7` (resolved, 1 occurrence(s)) |

**Probable causes**

- Caller omitted the X-API-Key header or sent it in the wrong format
- API key was rotated or revoked but the client still uses the old value
- Clock skew causing an expired JWT (check exp claim vs server time)
- Insufficient scope / role for the requested resource (403)

**Captured evidence**

| Field | Value |
|---|---|
| `http_status` | `401` |
| `error_type` | `none` |
| `latency_ms` | `2.72` |
| `latency_threshold_ms` | `3000.0` |
| `path` | `/secure-data` |
| `method` | `GET` |
| `request_id` | `lab-10556e280791` |
| `transport_error` | `HTTP 401` |

**Recommended actions**

1. Verify the X-API-Key header value against the key store
2. Check key expiry & rotation schedule; re-issue and redeploy the credential
3. Confirm the monitoring job's secret store is in sync after rotation
4. Add a pre-flight credential check to the synthetic monitor

## 3. Scenario 2 — API timeout

**Trigger**: `GET /simulate-timeout?seconds=12` with a client budget of 8 s — the client aborts while the server is still processing (a genuine timeout, not a slow 200).

| Item | Value |
|---|---|
| Observed | `HTTP no response` in 8009 ms |
| Rule | `TIMEOUT` (critical) |
| Category | `timeout` |
| Root cause | GET /simulate-timeout exceeded the 3000 ms timeout budget (observed 8009 ms) and the connection was aborted. |
| Owner | Backend Engineering |
| Confidence | high |
| Alerts | call:simulated, email:simulated, slack:simulated |
| Incident | `INC-20261101-FBB3D9` (open, 1 occurrence(s)) |

**Probable causes**

- Slow downstream dependency (database query, third-party API, cache miss storm)
- Blocking I/O inside the request path (sync call in async handler)
- Resource saturation - CPU throttling, connection-pool exhaustion, GC pause
- Network latency / packet loss between the monitor and the service

**Captured evidence**

| Field | Value |
|---|---|
| `http_status` | `None` |
| `error_type` | `timeout` |
| `latency_ms` | `8008.94` |
| `latency_threshold_ms` | `3000.0` |
| `path` | `/simulate-timeout` |
| `method` | `GET` |
| `request_id` | `lab-8764fccc1657` |
| `transport_error` | `request aborted: exceeded the 8s client timeout (server still processing)` |

**Recommended actions**

1. Check database slow-query log and add the missing index / query cache
2. Move blocking work to a background task or add an async client
3. Add or tighten upstream timeouts + circuit breaker so callers fail fast
4. Scale the service horizontally or raise the worker/connection pool size

## 4. Scenario 3 — Server error (HTTP 500)

**Trigger**: `GET /simulate-error` raises an unhandled `RuntimeError`.

| Item | Value |
|---|---|
| Observed | `HTTP 500` in 5 ms |
| Rule | `SERVER_ERROR` (critical) |
| Category | `server_error` |
| Root cause | Unhandled RuntimeError raised while serving GET /simulate-error: Simulated upstream failure: inventory service returned no data |
| Owner | Backend Engineering |
| Confidence | high |
| Alerts | call:simulated, email:simulated, slack:simulated |
| Incident | `INC-20261101-98052D` (open, 2 occurrence(s)) |

**Probable causes**

- Unhandled exception in route handler or a downstream dependency call
- Invalid assumption about input data (None / missing key / type mismatch)
- Downstream service or database returned an error that was not caught
- Recent deployment introduced a regression (check last deploy diff)

**Captured evidence**

| Field | Value |
|---|---|
| `http_status` | `500` |
| `error_type` | `none` |
| `latency_ms` | `9.11` |
| `latency_threshold_ms` | `3000.0` |
| `path` | `/simulate-error` |
| `method` | `GET` |
| `request_id` | `lab-8ee67bfed60f` |
| `transport_error` | `HTTP 500` |

**Recommended actions**

1. Inspect captured stack trace for request_id=lab-8ee67bfed60f (Dashboard -> Incidents -> Evidence)
2. Reproduce with the same payload in staging and add a regression test
3. Add explicit exception handling + structured logging around the failing call
4. Roll back the last release if the error started immediately after a deploy

## 5. Scenario 4 — Rate limit exceeded (HTTP 429)

**Trigger**: Rapid calls to `/simulate-rate-limit` (quota = 5 / 60 s).

| Item | Value |
|---|---|
| Observed | `HTTP 429` in 2 ms |
| Rule | `RATE_LIMIT` (warning) |
| Category | `rate_limit` |
| Root cause | GET /simulate-rate-limit returned HTTP 429: the caller exceeded the configured request quota for the current window. |
| Owner | API Platform |
| Confidence | high |
| Alerts | email:simulated, slack:simulated |
| Incident | `INC-20261101-B06041` (open, 2 occurrence(s)) |

**Probable causes**

- Client or monitor is sending more requests than the quota allows
- Retry storm after a previous failure (no exponential backoff / jitter)
- Quota is shared across services and another consumer consumed the budget

**Captured evidence**

| Field | Value |
|---|---|
| `http_status` | `429` |
| `error_type` | `none` |
| `latency_ms` | `0.2` |
| `latency_threshold_ms` | `3000.0` |
| `path` | `/simulate-rate-limit` |
| `method` | `GET` |
| `request_id` | `lab-a73e412fdce5` |
| `transport_error` | `live traffic failure on /simulate-rate-limit` |

**Recommended actions**

1. Honour the Retry-After header and apply exponential backoff with jitter
2. Reduce synthetic probe frequency or raise the endpoint quota
3. Introduce per-consumer quotas so one client cannot starve the others

## 6. Additional scenarios (beyond the four required)

| Scenario | Observed | Rule | Severity | Result |
|---|---|---|---|---|
| Latency SLO breach (> 3s) | HTTP 200 in 3504 ms | `SLOW_RESPONSE` | warning | detected in 6 ms — email:simulated, slack:simulated |
| Service health check failure | HTTP 503 in 4 ms | `HEALTH_CHECK_FAILED` | critical | detected in 6 ms — call:simulated, email:simulated, slack:simulated |
| API downtime (connection refused) | HTTP no response in 8 ms | `API_DOWN` | critical | detected in 8 ms — call:simulated, email:simulated, slack:simulated |

Root causes captured for the extra scenarios:

- **Latency SLO breach (> 3s)** — GET /simulate-timeout responded in 3504 ms which is above the 3000 ms latency SLO.
- **Service health check failure** — GET /health returned HTTP 503 - the service reported itself unhealthy because a readiness dependency failed its probe.
- **API downtime (connection refused)** — GET http://127.0.0.1:9/health is unreachable - connection refused: All connection attempts failed. The service process is not accepting connections.

## 7. Notification proof

Every dispatch is persisted. Current state of the running system:

| Channel | Records | Status |
|---|---|---|
| Email | 14 | `simulated` |
| Slack | 14 | `simulated` |
| Call | 7 | `simulated` |

Where to look:

1. **Dashboard** → Alerts → click **payload** on any row (Block Kit JSON / SMTP envelope / Twilio request).
2. **Files** → `backend/data/alert-outbox/alerts-<date>.jsonl` and `alerts.log`.
3. **API** → `GET /monitor/alerts`, `GET /monitor/alerts/outbox`.
4. **SQL** → `SELECT channel, status, delivery_note, created_at FROM alerts ORDER BY id DESC LIMIT 20;`
5. **Report** → `deliverables/alert-proof.md` (generated from the live system).

## 8. Automated test suite

```bash
cd backend && python -m pytest -q
# 22 passed
```

Coverage: sample endpoints (success + every failure mode), control-plane contracts, probe cycle, Prometheus exposition, scenario detection for six rules, traceback evidence, incident de-duplication and lifecycle, channel test dispatch, and runtime settings updates. The suite boots its own server on port 8123 with a private database, so it never touches development data.

## 9. How to reproduce

```bash
# terminal 1 - backend
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# terminal 2 - frontend (optional; the CLI does not need it)
cd frontend && npm run dev

# terminal 3 - run every scenario and write the evidence files
cd backend && python scripts/simulate_failures.py
# or interactively: dashboard -> Failure Lab -> "Run all scenarios"
```
