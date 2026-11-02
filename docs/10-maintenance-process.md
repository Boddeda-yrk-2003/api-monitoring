# Maintenance Process

Operational routines that keep APIGuard healthy: daily checks, weekly tuning,
monthly reviews, backup/restore, upgrades and change management.

---

## 1. Routine schedule

| Frequency | Task | Owner | Command / location |
|---|---|---|---|
| **Daily** | Verify service health & open incidents | On-call | `GET /monitor/summary`, Incidents view |
| **Daily** | Confirm the probe loop is running | On-call | `GET /monitor/engine/status` → `running: true`, cycles increasing |
| **Daily** | Check alert delivery (no `failed` rows) | On-call | `SELECT channel, status, COUNT(*) FROM alerts WHERE created_at > datetime('now','-1 day') GROUP BY 1,2;` |
| **Weekly** | Review SLOs: uptime, p95, error rate | Service owner | Overview (7d window), Grafana |
| **Weekly** | Tune thresholds / cooldowns | Service owner | Settings → thresholds |
| **Weekly** | Database maintenance | SRE | Retention SQL + `VACUUM` / `OPTIMIZE` |
| **Weekly** | Verify backups restore | SRE | See §3 |
| **Monthly** | Dependency & security updates | Service owner | `pip list --outdated`, `npm outdated`, `pip-audit` |
| **Monthly** | Game day: run all failure scenarios | Team | `python scripts/simulate_failures.py` |
| **Quarterly** | Review alert rules & routing | SRE + owner | `docs/07-alerting-guide.md` |
| **Quarterly** | Rotate API keys / webhook secrets | Security | `.env`, `VALID_API_KEYS` |

## 2. Health-check script

```bash
#!/usr/bin/env bash
# tools/healthcheck.sh - exits non-zero when the monitoring stack is unhealthy
set -euo pipefail
BASE="${1:-http://localhost:8000}"

curl -fsS "$BASE/health" > /dev/null                       && echo "health:      OK"  || { echo "health:      FAIL"; exit 1; }
curl -fsS "$BASE/monitor/engine/status" | grep -q '"running":true' && echo "engine:      OK"  || { echo "engine:      FAIL"; exit 1; }
curl -fsS "$BASE/metrics" | grep -q apiguard_service_up     && echo "metrics:     OK"  || { echo "metrics:     FAIL"; exit 1; }

OPEN=$(curl -fsS "$BASE/monitor/summary?window=1h" | python3 -c "import sys,json;print(json.load(sys.stdin)['open_incidents'])")
echo "open incidents: $OPEN"
[ "$OPEN" -eq 0 ] || exit 2
```

Wire it into cron / a systemd timer / an external uptime checker (UptimeRobot,
Better Uptime) pointing at `/health`.

## 3. Backup & restore

**SQLite (default)**

```bash
# backup (safe while running thanks to WAL)
sqlite3 backend/data/apiguard.db ".backup '/var/backups/apiguard-$(date +%F).db'"

# restore
systemctl stop apiguard            # or stop uvicorn
cp /var/backups/apiguard-2026-11-01.db backend/data/apiguard.db
systemctl start apiguard
```

**PostgreSQL**

```bash
pg_dump -Fc apiguard > apiguard-$(date +%F).dump
pg_restore -d apiguard apiguard-2026-11-01.dump
```

Retention: keep 7 daily + 4 weekly backups; test a restore every month.

## 4. Data retention & vacuum

```sql
-- run weekly (SQLite)
DELETE FROM checks       WHERE checked_at < datetime('now', '-72 hours');
DELETE FROM request_logs WHERE ts         < datetime('now', '-72 hours');
DELETE FROM error_logs   WHERE ts         < datetime('now', '-30 days');
PRAGMA wal_checkpoint(TRUNCATE);
VACUUM;
```

Keep `incidents` and `alerts` indefinitely — they are the compliance/audit trail.
Export long-term trends to Prometheus/Grafana or a warehouse instead.

## 5. Configuration management

- All tunables live in `app/core/config.py` and are overridable via `.env`.
- Never commit `.env`; commit `.env.example` with the full key list.
- Runtime changes (`PUT /monitor/settings`) are persisted in `settings_kv` and
  applied immediately — record them in the change log so the file and the DB do
  not drift.
- Secrets (Slack webhook, SMTP password, Twilio token) should come from a secret
  manager in production (Vault, AWS Secrets Manager, SSM Parameter Store).

## 6. Change management

| Change | Steps |
|---|---|
| Add a monitored endpoint | Insert into `endpoints` → restart not required → confirm the first probe in the Endpoints view |
| Add an alert rule | Implement (engine + RCA) → add unit tests → update `07-alerting-guide.md` → dry-run in staging → announce to the on-call rotation |
| Change a threshold | Update via Settings → observe for one probe cycle → document in the change log |
| Dependency upgrade | Virtualenv → run `pytest` → run `simulate_failures.py` → deploy |
| Schema change | Back up → apply → re-seed or migrate (Alembic recommended for production) → verify `/monitor/summary` |

## 7. Release checklist

1. `pytest -q` green (22 tests).
2. `python scripts/simulate_failures.py` → 7/7 detected.
3. Frontend builds: `npm run build`.
4. Docs updated (thresholds, rules, screenshots).
5. Backup taken.
6. Deploy with a single uvicorn worker (`--workers 1` keeps one probe loop).
7. Post-deploy: `/health` OK, engine running, one probe cycle executed, no
   unexpected open incidents.

## 8. On-call runbook (condensed)

1. **Alert received** (Slack / e-mail / call) → open the incident link.
2. **Read the RCA block** (root cause, probable causes, evidence, actions).
3. **Acknowledge** in the console → stops repeat notifications within the cooldown.
4. **Correlate** with the traceback (Alerts → Captured exceptions) and the
   `request_id` in `request_logs`.
5. **Mitigate** using the recommended actions (roll back, restart, scale, raise
   quota, rotate key…).
6. **Verify** the endpoint turns healthy; the incident auto-resolves after two
   healthy probes (or resolve manually).
7. **Post-mortem** — export the incident JSON, note the detection time, MTTA and
   MTTR, and add a regression test or a new alert rule if a gap was found.

## 9. Capacity & growth

| Signal | Watch | Action |
|---|---|---|
| `checks` rows/day | > 200 k | Raise `PROBE_INTERVAL_SECONDS` or move to PostgreSQL + partitioning |
| DB file size | > 2 GB | Enable the retention job, export old data |
| p95 latency trend | approaching the 3 s SLO | Profile before it breaches (see the RCA latency branch) |
| Alert volume | > 20 / day | Raise thresholds / cooldown; review noisy rules |
| Open incidents | consistently > 0 | Rules that never resolve → check recovery thresholds and the sweeper |

## 10. Decommissioning

1. Export `incidents` and `alerts` to JSON (`GET /monitor/incidents`, `/monitor/alerts`).
2. Archive `backend/data/alert-outbox/` and the SQLite file.
3. Stop the service, remove the Prometheus scrape config and Grafana dashboard.
4. Revoke the Slack webhook, SMTP credentials and API keys.
