# Product Requirements Document (PRD)
### APIGuard — API Monitoring Dashboard for a FastAPI Service

| Field | Value |
|---|---|
| Product name | APIGuard |
| Version | 1.0.0 |
| Document owner | Senior Software Engineer (implementation) |
| Status | Delivered |
| Last updated | 2026-11-01 |
| Tech stack | FastAPI · React (Vite) · SQLite · Prometheus · pytest |

---

## 1. Problem statement

Teams running REST APIs have no cheap, self-contained way to demonstrate — and
validate — that their monitoring actually works. Dashboards are typically wired
to a SaaS vendor, alerts are configured but never tested, and when an outage
happens nobody can answer *“why did this fail?”* quickly because the evidence
(status codes, latency, stack traces, request ids) lives in five different
places.

**APIGuard** is a complete, offline-runnable monitoring reference
implementation: a sample FastAPI service that can produce real success and
failure scenarios, a monitoring engine that observes it, a React dashboard that
visualises health, an alerting layer that notifies on Slack / e-mail / phone,
and a rule-based root cause analysis (RCA) engine that explains every failure.

## 2. Goals and non-goals

### Goals
| # | Goal | Success measure |
|---|---|---|
| G1 | Provide a sample REST API that can generate realistic success **and** failure scenarios | Endpoints for health, data, 500, timeout, 429, 401 exist and behave as documented |
| G2 | Monitor availability, latency, status codes, error rate and server health | Synthetic probe loop + real-traffic capture persisted on every request |
| G3 | Present a dashboard with uptime, response time, request volume, failures, error trends and live service status | 7 dashboard views driven by a documented REST control-plane API |
| G4 | Alert on downtime, latency > 3 s, HTTP 500, elevated failure rate and health-check failure | 8 alert rules; Slack + e-mail always, phone call for critical |
| G5 | Prove detection for 4 required scenarios (auth, timeout, 500, 429) | Automated test matrix: 7/7 detected, evidence exported |
| G6 | Deliver root cause information with every incident | RCA block (root cause, probable causes, evidence, remediation, owner) on 100 % of incidents |
| G7 | Ship complete documentation | PRD, DRD, DB schema, backend/frontend guides, alerting, runbook, maintenance |

### Non-goals
- Production-grade multi-tenant SaaS; single-service demo scope.
- Distributed tracing (OpenTelemetry) — correlation ids are provided instead.
- Kubernetes / Terraform deployment manifests (Docker-friendly layout is provided).
- Long-term metric storage beyond SQLite retention (72 h rolling cleanup target).

## 3. Personas

| Persona | Need | APIGuard feature |
|---|---|---|
| **Backend engineer** | Know when my endpoint breaks and why | Incident console with stack trace, failing frames, remediation steps |
| **SRE / on-call** | Get notified fast, with enough context to act | Severity-routed Slack / e-mail / voice alerts, acknowledgement workflow |
| **Engineering manager** | Report on reliability | Uptime %, error-rate trend, incident history with durations |
| **QA / test engineer** | Prove the monitoring works before a release | Failure Lab: one-click scenarios + exportable test matrix |

## 4. Functional requirements

### 4.1 Sample API (FastAPI)
| ID | Requirement | Implementation |
|---|---|---|
| FR-1.1 | Health endpoint | `GET /health` → status, version, uptime, DB state, checks recorded; `?degraded=true` forces 503 |
| FR-1.2 | Sample data endpoints | `GET /users`, `GET /products` (filtering + pagination), `GET /users/{id}` (404 path) |
| FR-1.3 | Error simulation | `GET /simulate-error` raises → HTTP 500 (with two failure modes) |
| FR-1.4 | Timeout simulation | `GET /simulate-timeout?seconds=N` (default 6 s) |
| FR-1.5 | Rate-limit simulation | `GET /simulate-rate-limit` → 429 after N requests / 60 s window, `Retry-After` header |
| FR-1.6 | Auth simulation | `GET /simulate-auth-error` → 401; `GET /secure-data` → 401 / 403 / 200 depending on `X-API-Key` |
| FR-1.7 | Correlation & timing | Every response carries `X-Request-ID` and `X-Response-Time` |

### 4.2 Monitoring
| ID | Requirement | Implementation |
|---|---|---|
| FR-2.1 | Synthetic probing | Background asyncio loop, default **10 s** interval, per-endpoint timeout budget |
| FR-2.2 | Real traffic capture | Middleware writes every request (method, path, status, latency, request id, IP, UA) |
| FR-2.3 | Availability tracking | Consecutive-failure counter per endpoint with configurable threshold |
| FR-2.4 | Latency tracking | avg / p95 / max per endpoint and per time bucket |
| FR-2.5 | Status-code & error-rate tracking | Rolling window (default 5 min) failure-rate computation |
| FR-2.6 | Server health | `/health` parsed every cycle; dedicated `HEALTH_CHECK_FAILED` rule |
| FR-2.7 | Prometheus exposition | `GET /metrics` with 8 metric families |
| FR-2.8 | Retention | Rolling cleanup target of 72 h for raw check rows |

### 4.3 Dashboard (React)
| ID | Requirement | Implementation |
|---|---|---|
| FR-3.1 | KPI cards | Uptime %, avg latency, total requests, failed requests, error rate, open incidents |
| FR-3.2 | Trend charts | Latency (avg/p95/max) + failed checks; check volume success vs failed |
| FR-3.3 | Distribution | HTTP status donut + legend |
| FR-3.4 | Endpoint health | Per-endpoint uptime, p95, error rate, sparkline, 24 h availability strip, raw probe table |
| FR-3.5 | Incidents | Filter by status/severity, RCA panel, acknowledge / resolve, JSON export |
| FR-3.6 | Alerts | Delivery history with exact provider payloads, channel test buttons, captured exceptions |
| FR-3.7 | Failure Lab | 7 scenarios, run individually or all; live result, RCA, alert badges, CSV/JSON export |
| FR-3.8 | Configurability | Time window (15 m → 7 d), runtime thresholds and channel credentials |
| FR-3.9 | Live behaviour | Auto-refresh (10–30 s per widget), manual refresh, “run probe now” |

### 4.4 Alerting
| ID | Requirement | Implementation |
|---|---|---|
| FR-4.1 | Rule catalogue | 8 rules (see §7 of the alerting guide) with severity mapping |
| FR-4.2 | De-duplication | One incident per (endpoint, rule); re-notify only after the cooldown (60 s) |
| FR-4.3 | Channels | Slack webhook, SMTP e-mail, Twilio voice call for critical |
| FR-4.4 | Dry-run proof | Unconfigured channels render the full payload and store it as `simulated` |
| FR-4.5 | Outbox | Every dispatch appended to `data/alert-outbox/alerts-<date>.jsonl` + `alerts.log` |

### 4.5 Root cause analysis
| ID | Requirement | Implementation |
|---|---|---|
| FR-5.1 | Automatic classification | Rule-based engine maps status / exception / latency / transport error → category |
| FR-5.2 | Evidence capture | Exception type, message, full traceback, failing frames, request id, thresholds |
| FR-5.3 | Remediation | 3–5 ranked recommended actions + owning team per incident |
| FR-5.4 | Confidence | `high` / `medium` per classification, surfaced in the UI and in notifications |

## 5. Non-functional requirements

| ID | Requirement | Target / implementation |
|---|---|---|
| NFR-1 | Setup time | `pip install -r requirements.txt` + `npm install`; first run seeds 24 h of history |
| NFR-2 | Detection latency | < 1 s from failure to incident + notification (measured: 6–14 ms) |
| NFR-3 | Dashboard responsiveness | Client-side polling; all aggregations are indexed SQL queries |
| NFR-4 | Portability | SQLite default; SQLAlchemy models are PostgreSQL-compatible |
| NFR-5 | Testability | 22 pytest cases covering API, control plane, detection, RCA and alerting |
| NFR-6 | Observability of the monitor itself | `/monitor/engine/status` (cycles, last cycle duration) |
| NFR-7 | Security | No credentials in code; secrets via env / `.env`; keys validated per request |
| NFR-8 | Accessibility & responsiveness | Dark-theme UI, keyboard-navigable, collapses to mobile nav below 1024 px |

## 6. Success criteria (definition of done)

| # | Criterion | Status |
|---|---|---|
| 1 | FastAPI sample API created and running | ✅ http://localhost:8000/docs |
| 2 | API monitoring configured | ✅ 4 endpoints probed every 10 s + live traffic capture |
| 3 | Dashboard shows health and performance metrics | ✅ 7 views, 9 charts |
| 4 | Alerts configured and tested | ✅ 8 rules, 3 channels, test endpoint, dry-run proof |
| 5 | Failure scenarios detected | ✅ 7/7 (incl. the 4 mandatory: auth, timeout, 500, 429) |
| 6 | Root cause information available | ✅ RCA block on every incident + captured stack traces |
| 7 | Documentation complete | ✅ 11 documents + inline OpenAPI |

## 7. Release scope

- **v1.0.0 (delivered)** — everything in this document.
- **Backlog** — Postgres + Timescale retention job, OpenTelemetry trace
  correlation, Terraform/Docker Compose deployment, PagerDuty and Teams
  channels, synthetic checks from multiple regions, SLO burn-rate alerts.
