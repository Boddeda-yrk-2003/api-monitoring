# Deliverables

Everything produced by the APIGuard build, ready to attach to a report or
submission.

| File / folder | What it is |
|---|---|
| **`demo.gif`** | Animated walkthrough: overview → endpoints → incident RCA → failure lab (live HTTP 500 detection) → alerts → settings → explorer |
| **`screenshots/01-overview.png`** | Dashboard KPIs, latency & failure trend, status donut, endpoint health, feeds |
| **`screenshots/02-endpoints.png`** | Per-endpoint SLOs, 24 h availability strip, raw probe records |
| **`screenshots/03-incidents-rca.png`** | Incident console with the full root-cause analysis panel |
| **`screenshots/04-failure-lab.png`** | Failure lab scenario catalogue (7 scenarios) |
| **`screenshots/05-failure-lab-result.png`** | Live result of a scenario: detection, RCA, dispatched alerts |
| **`screenshots/06-alerts.png`** | Alert history, notification channels, captured exceptions |
| **`screenshots/07-settings.png`** | Thresholds, channel credentials, active alert rules |
| **`screenshots/08-api-explorer.png`** | Calling the sample API from the dashboard |
| **`failure-test-results.json` / `.csv`** | Machine-readable results of all 7 scenarios (detection time, rule, RCA, alerts) |
| **`alert-proof.md`** | Notification proof: delivery log + exact Slack (Block Kit), e-mail and Twilio payloads |
| **`test-report.txt`** | pytest report — 22/22 passing (hermetic suite) |
| **`console-errors.log`** | Browser console check from the screenshot run (only dev-server HMR warnings) |

## How each artefact was produced

| Artefact | Command |
|---|---|
| Screenshots + GIF | `python tools/capture_demo.py --base http://localhost:5173` |
| Scenario results | `cd backend && python scripts/simulate_failures.py` |
| Results document | `python tools/generate_results_doc.py --base http://localhost:8000` |
| Alert proof | `deliverables/alert-proof.md` is generated from `GET /monitor/alerts` + `GET /monitor/alerts/outbox` |
| Test report | `cd backend && python -m pytest -q` |

Raw evidence also lives in the running system:

- `backend/data/alert-outbox/alerts-<date>.jsonl` — every dispatch (machine readable)
- `backend/data/alert-outbox/alerts.log` — every dispatch (human readable)
- `backend/data/apiguard.db` → tables `incidents`, `alerts`, `error_logs`

## Requirement traceability

| Requirement | Evidence |
|---|---|
| FastAPI API created & running | `screenshots/08-api-explorer.png`, Swagger at `/docs` |
| Monitoring configured | `screenshots/02-endpoints.png`, `01-overview.png` |
| Dashboard metrics | `screenshots/01-overview.png`, `03-incidents-rca.png` |
| Alerts configured & tested | `screenshots/06-alerts.png`, `alert-proof.md` |
| Failure scenarios detected | `failure-test-results.json`, `05-failure-lab-result.png`, `screenshots/03-…` |
| Root cause information | `screenshots/03-incidents-rca.png`, `docs/08-…`, per-incident RCA in the DB |
| Documentation complete | `docs/` — 10 documents + Grafana/Prometheus config |
