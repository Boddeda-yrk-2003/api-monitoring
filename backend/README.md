# APIGuard — Backend (FastAPI + monitoring engine)

The sample REST API **and** the monitoring stack that observes it, in one
process. See [`../docs/04-backend-guide.md`](../docs/04-backend-guide.md) for the
full guide.

## Run

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # optional
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

| URL | Content |
|---|---|
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/health | health endpoint |
| http://localhost:8000/metrics | Prometheus metrics |
| http://localhost:8000/monitor/summary | dashboard KPI API |

## Structure

```
app/
├── main.py               app factory, lifespan, global exception handler
├── database.py           SQLAlchemy engine/session
├── models.py             7 tables (endpoints, checks, request_logs, error_logs,
│                         incidents, alerts, settings_kv)
├── schemas.py            Pydantic v2 contracts
├── core/config.py        all settings (env / .env)
├── core/middleware.py    request id, timing, traffic logging, error capture
├── monitoring/
│   ├── engine.py         probe loop, alert rules, incident lifecycle
│   ├── rca.py            root cause analysis (9 categories)
│   ├── alerter.py        Slack / e-mail / Twilio rendering + delivery
│   ├── metrics.py        Prometheus families
│   ├── analytics.py      windowed aggregations for the dashboard
│   └── seed.py           endpoint catalogue + 24h demo history
└── routers/
    ├── sample.py         /health, /users, /products, /secure-data, /simulate-*
    └── monitor.py        /monitor/* control-plane API + failure lab
```

## Test & verify

```bash
python -m pytest -q                     # 22 tests
python scripts/simulate_failures.py     # 7 scenarios → data/failure-test-results.{json,csv}
python scripts/simulate_failures.py --only auth,rate_limit --auto-resolve
```

## Configuration highlights

| Variable | Default | Purpose |
|---|---|---|
| `PROBE_INTERVAL_SECONDS` | 10 | synthetic probe frequency |
| `LATENCY_THRESHOLD_MS` | 3000 | `SLOW_RESPONSE` SLO |
| `ERROR_RATE_THRESHOLD_PCT` | 5 | `HIGH_ERROR_RATE` |
| `DOWNTIME_CONSECUTIVE_FAILURES` | 2 | failures before `API_DOWN` |
| `ALERT_COOLDOWN_SECONDS` | 60 | re-notify throttle |
| `STALE_INCIDENT_MINUTES` | 15 | auto-resolve quiet incidents |
| `SLACK_WEBHOOK_URL` / `SMTP_*` / `TWILIO_*` | empty | dry-run until set |
| `DATABASE_URL` | `sqlite:///data/apiguard.db` | storage |

Full list: [`../docs/04-backend-guide.md`](../docs/04-backend-guide.md#4-configuration).
