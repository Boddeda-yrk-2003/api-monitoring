# Monitoring Architecture & Dashboard Configuration

## 1. Overview

APIGuard implements a **three-layer monitoring stack**:

```
┌───────────────────────────────────────────────────────────────────────────┐
│ LAYER 3 — Visualisation                                                    │
│   React dashboard (polling /monitor/*)   +   Grafana (scraping /metrics)   │
└───────────────────────────────────────────────────────────────────────────┘
                    ▲                                   ▲
                    │ REST/JSON                         │ Prometheus scrape
┌───────────────────────────────────────────────────────────────────────────┐
│ LAYER 2 — Collection & analytics                                           │
│   SQLite (checks, request_logs, error_logs)   ·   analytics.py aggregations│
│   Prometheus registry (9 metric families)                                  │
└───────────────────────────────────────────────────────────────────────────┘
                    ▲
┌───────────────────────────────────────────────────────────────────────────┐
│ LAYER 1 — Detection                                                        │
│   Synthetic probe loop (asyncio, 10s)   +   live-traffic middleware        │
│   → alert rules → incident lifecycle → RCA → notifications                 │
└───────────────────────────────────────────────────────────────────────────┘
```

## 2. What is monitored

| Signal | Source | Storage | Rule(s) |
|---|---|---|---|
| Availability | synthetic probe (`ok`, `error_type`) | `checks` | `API_DOWN` |
| Latency | probe round-trip | `checks.latency_ms` | `SLOW_RESPONSE`, `TIMEOUT` |
| HTTP status | probe + middleware | `checks`, `request_logs` | all rules |
| Error rate | rolling 5-min window | computed from `checks` | `HIGH_ERROR_RATE` |
| Failed requests | middleware (`status >= 400`) | `request_logs` | live-traffic rules |
| Server health | `/health` payload | `checks` on `/health` | `HEALTH_CHECK_FAILED` |
| Exceptions | global exception handler | `error_logs` | evidence for `SERVER_ERROR` |
| Notification health | dispatcher result | `alerts.status` | — |

## 3. Synthetic probing

- Runs as an `asyncio` task inside the FastAPI process (`MonitorEngine`).
- One `httpx.AsyncClient` per cycle, per-endpoint timeout budget of 10 s.
- Probes `/health`, `/users`, `/products`, `/secure-data` every 10 s.
  Chaos endpoints (`/simulate-*`) are excluded from the loop on purpose and are
  triggered on demand from the Failure Lab.
- Protected endpoints are probed with a valid `X-API-Key`; the auth-failure
  scenario calls the same path **without** the header.

**Cycle flow**

1. probe → persist `checks` row → update Prometheus gauges
2. evaluate rules (consecutive failures, latency, status, error rate, health)
3. open / update / resolve incidents
4. run RCA and refresh the evidence payload
5. dispatch notifications respecting the 60 s cooldown
6. evaluate live traffic (new `request_logs` rows)
7. sweep incidents quiet for > 15 minutes
8. refresh Prometheus incident gauges

## 4. Live-traffic detection

`RequestContextMiddleware` writes a `request_logs` row for every non-control-plane
request. `evaluate_live_traffic()` scans rows newer than the stored cursor
(`settings_kv.live_eval_last_id`) and raises incidents for 5xx / 429 / 401-403 /
408-504. This means a failure produced by a real user (or by the API Explorer) is
detected even if the synthetic probe has not reached that endpoint yet.

## 5. Dashboard configuration (React)

| Setting | Where | Default |
|---|---|---|
| Time window | TopBar chips | `24h` (15m · 1h · 6h · 24h · 7d) |
| Polling interval | `useApi(..., intervalMs)` | 15 s (summary), 20 s (charts), 30 s (traffic/alerts) |
| Manual refresh | TopBar ⟳ / **Run probe now** | remounts the active page |
| Thresholds | Settings page → `PUT /monitor/settings` | see §7 alerting guide |
| Channels | Settings page | dry-run until credentials are supplied |

Panels and their backing endpoints:

| Panel | Endpoint |
|---|---|
| KPI cards | `GET /monitor/summary` |
| Latency & failure trend | `GET /monitor/timeseries` |
| Check volume | `GET /monitor/timeseries` |
| Status distribution | `GET /monitor/traffic` |
| Endpoint cards | `GET /monitor/endpoints` |
| Uptime strip | `GET /monitor/endpoints/{id}/uptime` |
| Raw probe records | `GET /monitor/endpoints/{id}/checks` |
| Incident console | `GET /monitor/incidents` |
| Alert feed & payloads | `GET /monitor/alerts`, `/monitor/alerts/outbox` |
| Captured exceptions | `GET /monitor/errors` |
| Engine status | `GET /monitor/engine/status` |

## 6. Prometheus + Grafana (optional but fully supported)

### 6.1 Scrape configuration

`prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: apiguard
    metrics_path: /metrics
    static_configs:
      - targets: ['host.docker.internal:8000']   # use the container name in Docker
```

Run:

```bash
docker run -d --name prometheus -p 9090:9090 \
  -v "$PWD/docs/prometheus.yml:/etc/prometheus/prometheus.yml" prom/prometheus
```

Then open http://localhost:9090 and query, for example:

```promql
# availability per endpoint (5 min)
avg_over_time(apiguard_endpoint_up[5m])

# p95 latency (seconds)
histogram_quantile(0.95, sum by (le, endpoint) (
  rate(apiguard_monitor_check_duration_seconds_bucket[5m])))

# failed-check rate
sum(rate(apiguard_monitor_checks_total{outcome="failure"}[5m]))
  / sum(rate(apiguard_monitor_checks_total[5m]))

# inbound 5xx rate
sum(rate(apiguard_http_requests_total{status_code=~"5.."}[5m]))
```

### 6.2 Grafana

```bash
docker run -d --name grafana -p 3000:3000 grafana/grafana
```

1. **Connections → Data sources → Prometheus** → URL `http://prometheus:9090`
   (or `http://host.docker.internal:9090` outside Docker) → *Save & test*.
2. **Dashboards → New → Import** → upload `docs/grafana-dashboard.json`.
3. The dashboard contains: service status, uptime %, p95 latency, request rate,
   error-rate trend, endpoint availability table, status-code breakdown and
   open incidents by rule.

### 6.3 Grafana alerting (alternative to the built-in alerter)
Example rules you can create in Grafana on the scraped series:

| Alert | Expression | Condition |
|---|---|---|
| Endpoint down | `apiguard_endpoint_up == 0` | for 1m |
| Slow API | `histogram_quantile(0.95, rate(apiguard_monitor_check_duration_seconds_bucket[5m])) > 3` | for 2m |
| 5xx detected | `increase(apiguard_http_requests_total{status_code=~"5.."}[5m]) > 0` | for 0m |
| Service unavailable | `apiguard_service_up == 0` | for 1m |

The built-in alerter already covers these; Grafana alerting is recommended when
you want the notification to be owned by the visualisation layer.

## 7. Sizing & capacity

| Item | Value at defaults |
|---|---|
| Probe requests | 4 endpoints × 6/min ≈ 24 rpm |
| `checks` rows/day | ≈ 34 500 |
| `request_logs` rows | traffic-dependent (seed ≈ 16 000/day) |
| DB growth | ≈ 3–6 MB/day (SQLite, before retention) |
| Detection latency | measured 6–14 ms from failure to dispatched alert |

## 8. Failure modes of the monitor itself

| Risk | Mitigation |
|---|---|
| Process dies → no probing | Run under a supervisor; `/health` is also checked by an external prober in production |
| DB write contention | Short-lived sessions, WAL mode, writes off the event loop |
| Alert storm | Per (rule, endpoint) de-duplication + 60 s cooldown |
| Clock skew | All timestamps are UTC; windows are computed server-side |
