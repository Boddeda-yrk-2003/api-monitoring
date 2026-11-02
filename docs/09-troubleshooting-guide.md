# Troubleshooting Guide & Operations Runbook

Quick diagnostic paths for the API, the monitor, the dashboard, alerting and the
database. Start with §1 (triage), then jump to the matching section.

---

## 1. Triage flow

```
Dashboard shows a problem
   │
   ├─ Is it real traffic or synthetic?  → Overview: “Total requests” (real)
   │                                      vs “synthetic checks”
   ├─ Which endpoints?                  → Endpoints view (status pills)
   ├─ Which rule fired?                 → Incidents (rule_id + severity)
   ├─ Why?                              → RCA panel (root cause + evidence)
   ├─ Was anyone notified?              → Alerts (channel + status + payload)
   └─ Reproduce?                        → Failure Lab → matching scenario
```

Fast probes:

```bash
curl -s localhost:8000/health | jq
curl -s "localhost:8000/monitor/summary?window=1h" | jq
curl -s "localhost:8000/monitor/incidents?status=open" | jq
curl -s "localhost:8000/monitor/engine/status" | jq
```

---

## 2. Service & API issues

| Symptom | Likely cause | Fix |
|---|---|---|
| `curl: connection refused` on :8000 | Backend not running | `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| `/health` returns 500 | DB unreachable or an exception in the handler | Check the uvicorn log; verify `backend/data/` is writable; inspect `error_logs` |
| `422 Unprocessable Entity` | Invalid query parameter (e.g. `limit=0`) | Validate against `/docs` |
| `401` on `/secure-data` | Missing `X-API-Key` | `-H "X-API-Key: demo-api-key-123"` |
| `403` on `/secure-data` | Key not in `VALID_API_KEYS` | Add it to `.env` or `PUT /monitor/settings` |
| `429` from `/simulate-rate-limit` | Quota exhausted (5 / 60 s) | Wait 60 s or raise `RATE_LIMIT_MAX_REQUESTS` |
| `/simulate-error` never returns 500 | Global exception handler removed | Ensure `app/main.py` registers `@app.exception_handler(Exception)` |
| Responses lack `X-Request-ID` | Middleware not registered | `app.add_middleware(RequestContextMiddleware)` must be present |

## 3. Monitoring engine issues

| Symptom | Likely cause | Fix |
|---|---|---|
| No new checks recorded | Engine task not started / crashed | `GET /monitor/engine/status` → `running`; check the log for a traceback in the loop |
| Checks stop after an error | Loop exception (should be caught) | Restart; the loop logs and continues — inspect the log for repeated errors |
| Endpoint stuck “unknown” | No checks in the selected window, or the endpoint is disabled | Enable it in `endpoints` (`enabled=true`) |
| All endpoints report failures | `SELF_BASE_URL` wrong, or the service is bound elsewhere | Set `SELF_BASE_URL` to the reachable base URL |
| Latency always ~0 ms | Probing `127.0.0.1` from cache / wrong host | Confirm the probe URL (log the first cycle) |
| Timeouts on every probe | Probe timeout too small or the event loop blocked | Raise `REQUEST_TIMEOUT_SECONDS`; move blocking work off the loop |
| Incidents never resolve | Recovery threshold never met, or the sweeper is disabled | Check `RECOVERY_CONSECUTIVE_SUCCESSES`, `STALE_INCIDENT_MINUTES` |
| Incident re-alerts every cycle | Cooldown set to 0 | Raise `ALERT_COOLDOWN_SECONDS` (default 60) |
| Live traffic not detected | Cursor ahead of the rows, or the path is excluded from logging | Confirm `settings_kv.live_eval_last_id`; `/monitor/*` is intentionally not logged |

Force a cycle and watch the result:

```bash
curl -X POST localhost:8000/monitor/probe/now | jq '{ran, duration_ms, results: [.results[] | {path: .endpoint_id, ok, status_code, latency_ms}]}'
```

## 4. Dashboard issues

| Symptom | Likely cause | Fix |
|---|---|---|
| Blank page | JS error or backend unreachable | Open devtools console; confirm `http://localhost:5173/monitor/summary` returns JSON (proxy) |
| `net::ERR_CONNECTION_REFUSED` on `/monitor/*` | Backend down or wrong proxy target | Start the backend; check `vite.config.js` proxy target |
| Charts empty | No data in the selected window | Widen the window, or press **Run probe now** |
| Numbers frozen | Polling stopped after an error | Press ⟳ (refresh) or reload |
| Styles missing | Tailwind not installed/built | `npm install`, restart Vite |
| HMR websocket errors behind a tunnel | Dev-server HMR cannot reach the browser | Harmless; the app still works. For a clean console use `npm run build && npm run preview` |
| `403`/CORS errors | Backend `CORS_ORIGINS` excludes the front-end origin | Add the origin to `CORS_ORIGINS` |

## 5. Alerting issues

| Symptom | Likely cause | Fix |
|---|---|---|
| No alerts at all | Rule never fired, or the incident was within the cooldown | Verify with the Failure Lab; check `alerts` table |
| Alerts stuck `simulated` | Channel credentials not configured (expected in the demo) | Set the webhook/SMTP/Twilio variables (see `07-alerting-guide.md`) |
| `failed` status | Provider rejected the payload | Read `delivery_note`; for Slack check the webhook URL, for SMTP check the port/STARTTLS/app password |
| Slack shows nothing | Webhook revoked or wrong workspace | Re-create the incoming webhook |
| E-mail not delivered | SMTP blocked / spam / wrong port | Test with `python -m smtpd -n -c DebuggingServer localhost:1025` and `SMTP_PORT=1025` |
| Call channel never used | Only critical incidents call | Verify severity; run the `server_error` scenario |
| Too many alerts | Cooldown too short / thresholds too tight | Raise `ALERT_COOLDOWN_SECONDS`, `DOWNTIME_CONSECUTIVE_FAILURES`, `ERROR_RATE_THRESHOLD_PCT` |

Manual test:

```bash
curl -X POST "localhost:8000/monitor/notifications/test?channels=slack,email,call" | jq
```

## 6. Database issues

| Symptom | Likely cause | Fix |
|---|---|---|
| `database is locked` | Long write transaction / multiple processes | Ensure a single worker (`--workers 1`), WAL is enabled, keep sessions short |
| Huge DB file | No retention | Run the cleanup SQL (§4 of `03-database-schema.md`) |
| Timestamps look wrong | Timezone confusion | All timestamps are naive UTC; the frontend appends `Z` when parsing |
| Percentiles look odd | Too few samples in the window | Widen the window or lower `PROBE_INTERVAL_SECONDS` |
| Schema changed but the app errors | Table exists with the old shape | Delete `data/apiguard.db` and restart (it is re-created and re-seeded) |

Useful queries:

```bash
sqlite3 backend/data/apiguard.db
sqlite> SELECT path, ROUND(100.0*SUM(ok)/COUNT(*),2) uptime, ROUND(AVG(latency_ms),1) avg_ms
        FROM checks JOIN endpoints ON endpoints.id=checks.endpoint_id
        WHERE checked_at >= datetime('now','-1 hour') GROUP BY path;
sqlite> SELECT rule_id, severity, status, COUNT(*) FROM incidents GROUP BY 1,2,3;
sqlite> SELECT channel, status, COUNT(*) FROM alerts GROUP BY 1,2;
sqlite> SELECT ts, path, exception_type, substr(exception_message,1,80) FROM error_logs ORDER BY id DESC LIMIT 10;
```

## 7. Seeded demo data looks wrong

| Symptom | Fix |
|---|---|
| I want an empty database | Set `SEED_HISTORY_ON_STARTUP=false` (or delete `data/apiguard.db`) and restart |
| I want more/less history | `SEED_HISTORY_HOURS=48` |
| Charts are empty after a fresh install | Seeding runs only when `checks` is empty — delete the DB file to re-seed |
| Seeded rows are being detected as live failures | The seed parks the live-traffic cursor; if you insert rows manually, update `settings_kv.live_eval_last_id` |

## 8. Escalation & recovery checklist

1. **Confirm** — reproduce with `curl` and with the Failure Lab.
2. **Contain** — acknowledge the incident in the console (stops duplicate pages
   being re-sent within the cooldown window).
3. **Diagnose** — read the RCA block; open the captured traceback; correlate the
   `request_id` across `error_logs` and `request_logs`.
4. **Fix** — apply the recommended actions in order.
5. **Verify** — run `python scripts/simulate_failures.py --only <scenario>`; the
   endpoint should recover and the incident auto-resolve after two healthy probes.
6. **Record** — resolve the incident (duration is stored) and export the JSON for
   the post-mortem.

## 9. Known limitations

- The probe loop lives in the API process: if the process dies, monitoring stops
  with it. Production should add an external prober.
- Percentiles are computed in Python over the window (fine to ~100 k rows).
- SQLite is single-writer; use PostgreSQL for high write volume.
- Retention is documented, not yet scheduled as a background job.
