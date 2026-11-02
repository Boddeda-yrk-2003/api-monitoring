# Design Requirements Document (DRD)
### APIGuard — architecture, data flow and design decisions

| Field | Value |
|---|---|
| Version | 1.0.0 |
| Status | Approved / implemented |
| Last updated | 2026-11-01 |

---

## 1. System context

```
┌─────────────────────────────┐        ┌──────────────────────────────────────┐
│  React dashboard (Vite)     │  HTTP  │  FastAPI service (uvicorn)           │
│  overview · endpoints ·     │ ─────► │  /monitor/*  control plane  (REST)   │
│  incidents · alerts · lab   │ ◄───── │  /health /users /products … (sample) │
└─────────────────────────────┘        │  /metrics (Prometheus exposition)    │
                                       └──────────────────────────────────────┘
        ▲                                        │            │            │
        │ polling (10–30 s)                      │            │            │
        │                              ┌─────────▼──┐  ┌──────▼─────┐  ┌───▼────────┐
        │                              │ Monitor    │  │ SQLite DB  │  │ Slack/SMTP/│
        │                              │ engine     │  │ (7 tables) │  │ Twilio     │
        │                              │ (asyncio)  │  └────────────┘  └────────────┘
        │                              └────────────┘
        │                                     ▲
        └─────────────────────────────────────┘  (dashboard reads the same DB
                                                  through the control plane)
```

The design deliberately keeps **one process** for the API and the monitor: the
monitoring loop runs as an `asyncio` task inside the FastAPI application, which
means a single `uvicorn` command starts the entire observable system.

## 2. Architectural principles

| # | Principle | Consequence |
|---|---|---|
| P1 | **Self-contained** | No external service is required to demo the whole loop; every integration degrades to dry-run |
| P2 | **Two detection paths** | *Synthetic* probes (pull) for availability/SLOs and *live traffic* (push, from middleware) for real user impact |
| P3 | **Evidence first** | Nothing is alerted without captured evidence; every incident row carries its own RCA payload |
| P4 | **Explainable automation** | The RCA engine is rule-based and documented, not a black-box model |
| P5 | **Idempotent operations** | Seeding, probing and alerting are safe to repeat; incidents de-duplicate by (endpoint, rule) |
| P6 | **Config at runtime** | Thresholds and channel credentials are mutable through the API without a restart |

## 3. Backend design

### 3.1 Module map

```
backend/app
├── main.py                    FastAPI app, lifespan, global exception handler
├── core/
│   ├── config.py              pydantic-settings (env + .env) — all tunables
│   └── middleware.py          RequestContextMiddleware: ids, timing, logging, error capture
├── database.py                engine / session / declarative base (SQLite pragmas)
├── models.py                  7 ORM tables (see DATABASE_SCHEMA.md)
├── schemas.py                 Pydantic v2 contracts for every endpoint
├── monitoring/
│   ├── engine.py              probe loop, alert rules, incident lifecycle
│   ├── rca.py                 rule-based root cause analysis
│   ├── alerter.py             render + deliver notifications (Slack/Email/Call/Outbox)
│   ├── metrics.py             Prometheus metric families
│   ├── analytics.py           windowed aggregations for the dashboard
│   └── seed.py                endpoint catalogue + 24 h demo history
└── routers/
    ├── sample.py              the monitored sample API
    └── monitor.py             control-plane REST API (dashboard + failure lab)
```

### 3.2 Request lifecycle

1. `RequestContextMiddleware` assigns/reuses `X-Request-ID`, starts a timer.
2. Route handler executes.
3. On success → response headers (`X-Request-ID`, `X-Response-Time`), a
   `request_logs` row, Prometheus counter + histogram.
4. On exception → traceback captured into `error_logs`, then the global handler
   returns a structured 500 JSON (`exception_type`, `request_id`, `path`).
5. Control-plane paths (`/monitor`, `/metrics`, `/docs`) are excluded from
   traffic logging so monitoring traffic does not pollute the monitored traffic.

### 3.3 Monitoring loop

```
run_cycle()
 ├── for each enabled endpoint:  probe → persist Check → evaluate rules
 │                                                        ├── open / update incident
 │                                                        ├── RCA analysis
 │                                                        └── dispatch alerts (cooldown-aware)
 ├── evaluate_live_traffic()   scan new request_logs rows for 4xx/5xx/429
 ├── sweep_stale_incidents()   auto-resolve incidents quiet for > 15 min
 └── refresh_gauges()          Prometheus gauges (open incidents, service up)
```

**Timing parameters (defaults):**

| Parameter | Default | Purpose |
|---|---|---|
| `PROBE_INTERVAL_SECONDS` | 10 | Synthetic probe frequency |
| `REQUEST_TIMEOUT_SECONDS` | 10 | Probe timeout budget |
| `DOWNTIME_CONSECUTIVE_FAILURES` | 2 | Failures before `API_DOWN` |
| `RECOVERY_CONSECUTIVE_SUCCESSES` | 2 | Successes before auto-resolve |
| `LATENCY_THRESHOLD_MS` | 3000 | `SLOW_RESPONSE` SLO |
| `ERROR_RATE_THRESHOLD_PCT` | 5 | `HIGH_ERROR_RATE` |
| `ERROR_RATE_WINDOW_MINUTES` | 5 | Rolling window for the error rate |
| `ALERT_COOLDOWN_SECONDS` | 60 | Re-notify throttle per (rule, endpoint) |
| `STALE_INCIDENT_MINUTES` | 15 | Auto-resolve quiet incidents |

### 3.4 Concurrency model
- The probe loop is a single `asyncio.Task`; HTTP probes use a shared
  `httpx.AsyncClient` per cycle.
- All database work runs through `run_in_threadpool` so a slow SQLite write
  never blocks the event loop.
- Sessions are short-lived (`SessionLocal()` per unit of work); ORM objects are
  never passed across session boundaries — ids are (see `record_manual_result`).

### 3.5 Root cause analysis engine

`rca.analyse()` maps a failure onto a diagnosis with **explicit rule
precedence** (health → 5xx → timeout → latency → auth → rate limit → transport →
error-rate → 4xx). Each branch returns:

| Field | Meaning |
|---|---|
| `category` | `authentication`, `timeout`, `latency`, `server_error`, `rate_limit`, `availability`, `health`, `error_rate`, `client_error` |
| `root_cause` | One-sentence explanation containing the observed values |
| `probable_causes` | 3–4 ranked hypotheses |
| `evidence` | Status, latency, thresholds, exception type/message, **traceback**, failing frames, request id, detection source |
| `recommended_actions` | 3–5 ordered remediation steps |
| `owner_team` | Routing hint (Backend / SRE / Security / API Platform) |
| `root_cause_confidence` | `high` when a traceback or a definitive status code is present |

### 3.6 Failure lab design

`POST /monitor/simulate/{scenario}` performs the real client call (including a
deliberate client-side abort for the timeout scenario) and then feeds the
observed result into `record_manual_result()` so detection is **deterministic
and immediate** — the demo never waits for the next probe cycle, and the same
code path (rules → RCA → alerting) is exercised as in production.

## 4. Frontend design

### 4.1 Technology choices
| Choice | Reason |
|---|---|
| React 18 + Vite 5 | Fast HMR, single-command dev server with proxying |
| Tailwind CSS 3 | Utility-first theming; dark glassmorphism without a component library |
| Recharts | Declarative, themeable charts compatible with React 18 |
| lucide-react | Consistent 24 px icon set, tree-shakeable |
| Hash routing | Zero-dependency, shareable URLs (`/#incidents`) |
| Polling (no WebSocket) | Matches the monitoring cadence; keeps the preview proxy simple |

### 4.2 Design language
- **Palette**: deep navy canvas (`#070B16`) with indigo/cyan/violet radial
  glows; semantic colours emerald (healthy), amber (warning), rose (critical).
- **Surfaces**: 16 px radius cards, 1 px `white/7%` borders, backdrop blur,
  gradient glow on hover, subtle grid overlay behind the content.
- **Motion**: `fadeUp` entrance, `pulseRing` on live status dots, `shimmer`
  skeletons, 200–300 ms transitions.
- **Data density**: KPI cards → trend charts → per-entity tables → raw records,
  i.e. summary first, evidence on demand (drawers/modals).

### 4.3 Component structure
```
App                       shell, window state, hash routing, toasts, refresh
├── Sidebar / MobileNav   navigation + live service summary
├── TopBar                title, window chips, refresh, “run probe now”
└── pages/
    Overview              KPIs, latency/volume charts, status donut, endpoint cards, feed
    Endpoints             endpoint list + detail (uptime strip, latency, raw checks)
    Incidents             filters + list + RCA panel + workflow actions
    Alerts                channels, alert history, payload modals, captured exceptions
    FailureLab            scenario cards, live result, test matrix, exports
    Explorer              call the sample API directly
    Settings              thresholds, channels, active rule catalogue
shared: ui.jsx (pills, cards, sparkline, uptime strip, table, tooltip)
        charts.jsx (latency, request volume, status donut)
        RcaPanel.jsx (root cause presentation)
```

### 4.4 State & data fetching
- `useApi(fetcher, deps, intervalMs)` — one hook for polling, manual refresh,
  loading and error state; interval `0` disables polling.
- Page-level remount (`key={page-nonce}`) is used for a global refresh so all
  widgets refetch consistently.
- Optimistic toasts (`pushToast`) for user-initiated actions.

## 5. Data design (summary)

See **`03-database-schema.md`** for the full DDL. Seven tables:

`endpoints` → `checks` (synthetic) · `request_logs` (real traffic) ·
`error_logs` (tracebacks) → `incidents` → `alerts`, plus `settings_kv` for
runtime configuration.

Key decisions:
- **Naive UTC timestamps** everywhere so SQLite and PostgreSQL behave
  identically; the frontend re-attaches `Z` when parsing.
- **Percentiles computed in Python** (SQLite has no `percentile_cont`); buckets
  use `strftime('%s', ts) / bucket_seconds` integer division.
- **JSON columns** (`probable_causes`, `evidence`, `recommended_actions`,
  `payload`) keep the RCA self-contained on the incident row — an incident is
  portable without joins.

## 6. Security & compliance design
- Secrets only via environment variables / `.env`; `.env.example` documents
  every key; nothing is committed with credentials.
- API keys are compared against a configurable allow-list; 401 (missing) vs
  403 (invalid) is distinguished on purpose.
- Rate limiting is per client IP with a sliding window and `Retry-After`.
- Alert payloads never include credentials or full request bodies.
- CORS is configurable (`CORS_ORIGINS`), default `*` for local development.

## 7. Error handling & resilience
| Failure | Handling |
|---|---|
| Unhandled exception in a route | Captured into `error_logs`, structured 500, monitor raises `SERVER_ERROR` |
| Monitor loop exception | Caught and logged per cycle; the loop never exits |
| Notification channel failure | Status recorded as `failed` with the provider message; incident still created |
| Database write failure in logging | Swallowed — telemetry must never break a request |
| Endpoint unreachable | `API_DOWN` with transport error text as evidence |

## 8. Extensibility points
1. **New alert rule** → add to `RULE_SEVERITY`, `RULE_CATALOG`, the evaluation
   function and an `rca.analyse()` branch.
2. **New channel** → add a renderer + transport in `alerter.py` and a card in
   the Alerts page.
3. **New datasource** → the models are PostgreSQL-ready; only the bucket
   expression in `analytics.py` needs `date_trunc`.
4. **Grafana** → scrape `/metrics`; a ready-made dashboard JSON is provided.

## 9. Open questions / assumptions
- **Assumption**: a single-region, single-instance deployment; the probe loop is
  in-process, so if the process dies, monitoring dies with it (acceptable for a
  demo; production would use an external prober).
- **Assumption**: 24 h of seeded demo history is desirable on first boot
  (disable with `SEED_HISTORY_ON_STARTUP=false`).
- **Open**: retention enforcement is documented as a 72 h target; the cleanup
  helper is a scheduled-job candidate rather than a background task.
