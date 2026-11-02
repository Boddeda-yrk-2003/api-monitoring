# Backend Guide — FastAPI service & monitoring engine

Everything you need to install, run, configure, extend and test the backend.

---

## 1. Requirements

| Requirement | Version |
|---|---|
| Python | 3.10+ (developed and tested on 3.13) |
| pip | any recent |
| OS | Linux / macOS / Windows (WSL) |
| Optional | SQLite CLI (`sqlite3`) for ad-hoc queries |

## 2. Setup (from scratch)

```bash
cd api-monitoring/backend

# 1. virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. dependencies
pip install -r requirements.txt

# 3. configuration (optional — sensible defaults are built in)
cp .env.example .env               # then edit thresholds / credentials

# 4. run
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

First boot prints the seed summary and starts the probe loop:

```
[apiguard] history seed: {'status': 'seeded', 'checks': 5764, 'request_logs': 16163, 'incidents': 5, 'alerts': 12, 'hours': 24}
[apiguard] APIGuard - API Monitoring Service v1.0.0 ready on 0.0.0.0:8000 (probe every 10s)
```

Open:

| URL | Content |
|---|---|
| http://localhost:8000/docs | Swagger UI (full OpenAPI reference) |
| http://localhost:8000/ | service index |
| http://localhost:8000/health | health payload |
| http://localhost:8000/metrics | Prometheus exposition |
| http://localhost:8000/monitor/summary | dashboard KPI rollup |

### Windows / PowerShell note
Use `python` instead of `python3` and `.venv\Scripts\Activate.ps1`.

## 3. Project layout

```
backend/
├── app/
│   ├── main.py               app factory, lifespan, global exception handler
│   ├── database.py           engine, session, declarative base
│   ├── models.py             ORM models (7 tables)
│   ├── schemas.py            Pydantic v2 contracts
│   ├── core/
│   │   ├── config.py         settings (env / .env)
│   │   └── middleware.py     request id, timing, traffic logging, error capture
│   ├── monitoring/
│   │   ├── engine.py         probe loop, rules, incident lifecycle
│   │   ├── rca.py            root cause analysis
│   │   ├── alerter.py        Slack / e-mail / call rendering + delivery
│   │   ├── metrics.py        Prometheus families
│   │   ├── analytics.py      windowed aggregations
│   │   └── seed.py           catalogue + 24 h demo history
│   └── routers/
│       ├── sample.py         the monitored sample API
│       └── monitor.py        control-plane API
├── scripts/simulate_failures.py   CLI failure-simulation runner
├── tests/                    pytest suite (22 cases)
├── data/                     SQLite DB + alert outbox (created at runtime)
├── requirements.txt
└── .env.example
```

## 4. Configuration

All settings live in `app/core/config.py` and can be overridden with
environment variables or a `.env` file.

| Variable | Default | Description |
|---|---|---|
| `HOST` / `PORT` | `0.0.0.0` / `8000` | bind address |
| `SELF_BASE_URL` | `http://127.0.0.1:8000` | base URL the monitor probes |
| `PROBE_INTERVAL_SECONDS` | `10` | synthetic check frequency |
| `REQUEST_TIMEOUT_SECONDS` | `10` | probe timeout budget |
| `LATENCY_THRESHOLD_MS` | `3000` | `SLOW_RESPONSE` threshold |
| `ERROR_RATE_THRESHOLD_PCT` | `5` | `HIGH_ERROR_RATE` threshold |
| `ERROR_RATE_WINDOW_MINUTES` | `5` | rolling window |
| `DOWNTIME_CONSECUTIVE_FAILURES` | `2` | failures before `API_DOWN` |
| `RECOVERY_CONSECUTIVE_SUCCESSES` | `2` | successes before auto-resolve |
| `ALERT_COOLDOWN_SECONDS` | `60` | re-notify throttle |
| `STALE_INCIDENT_MINUTES` | `15` | auto-resolve quiet incidents |
| `SEED_HISTORY_ON_STARTUP` | `true` | seed 24 h of demo data |
| `SEED_HISTORY_HOURS` | `24` | history length |
| `VALID_API_KEYS` | `demo-api-key-123,monitoring-key-456` | accepted `X-API-Key` values |
| `RATE_LIMIT_MAX_REQUESTS` | `5` | quota per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | quota window |
| `SIMULATED_TIMEOUT_SECONDS` | `6` | default sleep in `/simulate-timeout` |
| `DATABASE_URL` | `sqlite:///backend/data/apiguard.db` | SQLAlchemy URL |
| `SLACK_WEBHOOK_URL` / `SLACK_CHANNEL_LABEL` | empty / `#api-alerts` | Slack delivery |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO` | empty | e-mail delivery |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `ALERT_CALL_TO_NUMBER` | empty | voice-call delivery |
| `CORS_ORIGINS` | `*` | comma-separated allow-list |

> **Dry-run mode:** any channel left unconfigured still renders the complete
> payload and stores it with status `simulated` — that is the notification proof
> used in the deliverables.

## 5. Sample API reference

| Method & path | Success | Failure modes |
|---|---|---|
| `GET /health` | 200 – status, version, uptime, DB state, checks recorded | `?degraded=true` → 503 |
| `GET /users?limit=N` | 200 – up to 24 users | 422 on invalid `limit` |
| `GET /users/{id}` | 200 – one user | 404 when unknown |
| `GET /products?limit=N&category=` | 200 – up to 36 products | 422 on invalid `limit` |
| `GET /secure-data` | 200 with `X-API-Key` | 401 missing · 403 invalid |
| `GET /simulate-error` | — | 500 (`RuntimeError` / `KeyError` with `?mode=dependency`) |
| `GET /simulate-timeout?seconds=N` | 200 after N seconds | client timeout when N > client budget |
| `GET /simulate-rate-limit` | 200 with remaining quota | 429 + `Retry-After` after the quota |
| `GET /simulate-auth-error` | — | 401 always |
| `GET /metrics` | Prometheus text | — |

Every response carries `X-Request-ID` and `X-Response-Time`.

```bash
curl -s localhost:8000/health | jq
curl -s localhost:8000/users?limit=2 | jq
curl -s localhost:8000/secure-data -H "X-API-Key: demo-api-key-123" | jq
curl -i localhost:8000/simulate-error
```

## 6. Monitoring control-plane API

| Method & path | Purpose |
|---|---|
| `GET /monitor/summary?window=24h` | KPI rollup (uptime, latency, requests, failures, incidents) |
| `GET /monitor/timeseries?window=&endpoint_id=` | per-bucket latency + failed checks |
| `GET /monitor/endpoints?window=` | per-endpoint health, sparkline, uptime |
| `GET /monitor/endpoints/{id}/uptime?hours=24` | 30-minute availability slots |
| `GET /monitor/endpoints/{id}/checks?limit=100` | raw probe records |
| `GET /monitor/traffic?window=` | traffic by path + status distribution |
| `GET /monitor/incidents?status=&severity=&limit=` | incidents (RCA included) |
| `GET /monitor/incidents/{id}` | one incident |
| `POST /monitor/incidents/{id}/acknowledge` | set `acknowledged` |
| `POST /monitor/incidents/{id}/resolve` | resolve + duration |
| `GET /monitor/alerts?channel=&limit=` | notification history |
| `GET /monitor/alerts/outbox` | raw outbox records (proof) |
| `GET /monitor/errors?limit=` | captured exceptions |
| `GET /monitor/engine/status` | cycles, interval, last-cycle duration |
| `POST /monitor/probe/now` | run a probe cycle immediately |
| `GET /monitor/scenarios` | failure-lab catalogue |
| `POST /monitor/simulate/{scenario}` | run a scenario end-to-end |
| `GET` / `PUT /monitor/settings` | read / update thresholds and channels |
| `POST /monitor/notifications/test?channels=slack,email,call` | send test alerts |

Windows: `15m · 1h · 6h · 24h · 7d · 30d`.

## 7. Prometheus metrics

| Metric | Type | Labels |
|---|---|---|
| `apiguard_http_requests_total` | counter | `method`, `path`, `status_code` |
| `apiguard_http_request_duration_seconds` | histogram | `method`, `path` |
| `apiguard_monitor_checks_total` | counter | `endpoint`, `outcome`, `status_code` |
| `apiguard_monitor_check_duration_seconds` | histogram | `endpoint` |
| `apiguard_endpoint_up` | gauge | `endpoint` |
| `apiguard_endpoint_latency_seconds` | gauge | `endpoint` |
| `apiguard_incidents_open` | gauge | `rule` |
| `apiguard_alerts_delivered_total` | counter | `channel`, `status` |
| `apiguard_service_up` | gauge | — |

```bash
curl -s localhost:8000/metrics | grep apiguard
```

A ready-to-import Grafana dashboard is provided in
`docs/grafana-dashboard.json` (see `06-monitoring-architecture.md`).

## 8. Running the tests

```bash
cd backend
python -m pytest -q                     # 22 tests
python -m pytest -q -k scenario         # detection scenarios only
```

The suite uses a separate database (`data/apiguard_test.db`), disables history
seeding and freezes the probe interval.

## 9. Running the failure simulation from the CLI

```bash
python scripts/simulate_failures.py                          # all scenarios
python scripts/simulate_failures.py --only auth,rate_limit   # subset
python scripts/simulate_failures.py --auto-resolve           # tidy up after
```

Artefacts: `data/failure-test-results.json`, `data/failure-test-results.csv`
and a timestamped run copy. Exit code `0` when every scenario was detected.

## 10. Extending the backend

**Add an endpoint to monitor** — insert a row into `endpoints`
(`enabled=true`, `expected_status`, `latency_threshold_ms`), or add it to
`ENDPOINTS` in `app/monitoring/seed.py`.

**Add an alert rule** —
1. `app/monitoring/engine.py`: add to `RULE_SEVERITY` and to the evaluation
   logic (`evaluate_endpoint` / `record_manual_result`).
2. `app/monitoring/rca.py`: add to `RULE_CATALOG` and a classification branch.
3. `docs/07-alerting-guide.md`: document the trigger.

**Add a notification channel** —
1. `app/monitoring/alerter.py`: renderer + `_send_<channel>` transport.
2. Extend `_channels_for()` in `engine.py` if the routing should change.
3. Add a card in the frontend Alerts page.

**Change retention** — schedule the SQL in `03-database-schema.md` §4 (cron,
APScheduler or a systemd timer).

## 11. Production notes
- Run behind `gunicorn -k uvicorn.workers.UvicornWorker` or a process manager;
  the monitoring loop starts with the app (`--workers 1` keeps a single prober).
- Put `/metrics` behind network policy; it is unauthenticated by default.
- Move `SELF_BASE_URL` to the service's real internal URL.
- For high volume, switch to PostgreSQL and enable the retention job.
