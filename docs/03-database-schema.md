# Database Schema
### APIGuard · SQLite (PostgreSQL-compatible) data model

| Field | Value |
|---|---|
| Engine | SQLite 3 (WAL mode) — default file `backend/data/apiguard.db` |
| ORM | SQLAlchemy 2.0 declarative |
| Connection string | `sqlite:///…` (override with `DATABASE_URL`, e.g. `postgresql+psycopg://user:pass@host/db`) |
| Conventions | Naive-UTC `DATETIME`, surrogate integer PKs, `JSON` columns for RCA payloads |

---

## 1. Entity relationship diagram

```
┌──────────────┐      1:N      ┌────────────┐
│  endpoints   │──────────────►│   checks   │  synthetic probe results
│  (catalogue) │               └────────────┘
│              │      1:N      ┌────────────────┐
│              │──────────────►│  incidents     │  deduplicated failures + RCA
└──────────────┘               │                │      1:N
                               └────────────────┘──────►┌──────────┐
                                                        │  alerts  │  notifications
┌───────────────┐   (no FK — written by middleware)     └──────────┘
│ request_logs  │  real inbound traffic
└───────────────┘
┌───────────────┐   (no FK — written by the error handler)
│  error_logs   │  captured exceptions + tracebacks
└───────────────┘
┌───────────────┐
│ settings_kv   │  runtime thresholds + channel credentials
└───────────────┘
```

`request_logs` and `error_logs` are intentionally **not** linked by foreign key:
they are written on the request hot path by middleware/exception handlers and
must never be blocked by catalogue changes.

---

## 2. Table definitions

### 2.1 `endpoints` — monitored API catalogue

| Column | Type | Default | Notes |
|---|---|---|---|
| `id` | INTEGER PK | auto | |
| `name` | VARCHAR(120) NOT NULL | | Display name |
| `path` | VARCHAR(255) NOT NULL | | e.g. `/users` |
| `method` | VARCHAR(10) | `GET` | |
| `description` | TEXT | `''` | Shown in the UI |
| `group_name` | VARCHAR(60) | `core` | `core` / `security` / `chaos` |
| `expected_status` | INTEGER | `200` | Probe passes when the status matches |
| `latency_threshold_ms` | FLOAT | `3000` | Per-endpoint SLO (overrides the global) |
| `enabled` | BOOLEAN | `true` | `false` for chaos endpoints (not probed continuously) |
| `criticality` | VARCHAR(20) | `medium` | `low` / `medium` / `high` / `critical` |
| `created_at` | DATETIME | now(UTC) | |

**Constraints**: `UNIQUE(method, path)`.
**Seeded rows**: 8 (4 actively probed: `/health`, `/users`, `/products`,
`/secure-data`; 4 chaos: `/simulate-error`, `/simulate-timeout`,
`/simulate-rate-limit`, `/simulate-auth-error`).

### 2.2 `checks` — synthetic probe results

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `endpoint_id` | INTEGER FK → `endpoints.id` | indexed |
| `checked_at` | DATETIME | indexed |
| `ok` | BOOLEAN | indexed; `true` when status == expected and no transport error |
| `status_code` | INTEGER NULL | `NULL` for timeouts / connection errors |
| `latency_ms` | FLOAT | round-trip duration |
| `error_type` | VARCHAR(40) | `none` / `timeout` / `connection` / `dns` / `http_error` |
| `error_message` | TEXT | transport error or “unexpected status N” |
| `request_id` | VARCHAR(64) | correlates with `error_logs` / `request_logs` |
| `source` | VARCHAR(20) | `synthetic` |

**Volume**: 1 row per endpoint per probe (≈ 8 640 / endpoint / day at 10 s).

### 2.3 `request_logs` — real inbound traffic

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `ts` | DATETIME | indexed |
| `method` | VARCHAR(10) | |
| `path` | VARCHAR(255) | indexed |
| `status_code` | INTEGER | indexed |
| `latency_ms` | FLOAT | |
| `request_id` | VARCHAR(64) | indexed |
| `client_ip` | VARCHAR(64) | |
| `user_agent` | VARCHAR(255) | |
| `is_error` | BOOLEAN | indexed; `status_code >= 400` |

Written by `RequestContextMiddleware`; `/monitor`, `/metrics`, `/docs` are
excluded so control-plane traffic is not counted as API traffic.

### 2.4 `error_logs` — captured exceptions (RCA evidence)

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `ts` | DATETIME | indexed |
| `request_id` | VARCHAR(64) | indexed; looked up by the RCA engine |
| `method` | VARCHAR(10) | |
| `path` | VARCHAR(255) | indexed |
| `exception_type` | VARCHAR(120) | e.g. `RuntimeError` |
| `exception_message` | TEXT | |
| `traceback` | TEXT | full, sanitised traceback |
| `status_code` | INTEGER | `500` |
| `client_ip` | VARCHAR(64) | |
| `latency_ms` | FLOAT | |

### 2.5 `incidents` — deduplicated failures with root cause analysis

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `public_id` | VARCHAR(32) UNIQUE | `INC-YYYYMMDD-XXXXXX`, shown in alerts |
| `endpoint_id` | INTEGER NULL FK | `NULL` for synthetic-host failures (e.g. downtime drill) |
| `rule_id` | VARCHAR(60) | `API_DOWN`, `SERVER_ERROR`, `TIMEOUT`, `HEALTH_CHECK_FAILED`, `SLOW_RESPONSE`, `HIGH_ERROR_RATE`, `AUTH_FAILURE`, `RATE_LIMIT`, `CLIENT_ERROR` |
| `title` | VARCHAR(255) | |
| `severity` | VARCHAR(20) | `info` / `warning` / `critical` |
| `status` | VARCHAR(20) | `open` / `acknowledged` / `resolved` |
| `category` | VARCHAR(40) | RCA category |
| `endpoint_path` | VARCHAR(255) | denormalised for display |
| `http_status` | INTEGER NULL | |
| `latency_ms` | FLOAT NULL | |
| `error_type` | VARCHAR(40) | |
| `root_cause` | TEXT | one-sentence explanation |
| `root_cause_confidence` | VARCHAR(20) | `high` / `medium` |
| `probable_causes` | JSON | array of strings |
| `evidence` | JSON | status, latency, thresholds, exception, traceback, request id… |
| `recommended_actions` | JSON | array of strings |
| `owner_team` | VARCHAR(80) | routing hint |
| `detected_at` | DATETIME | indexed |
| `last_seen_at` | DATETIME | bumped on every recurrence |
| `resolved_at` | DATETIME NULL | |
| `occurrences` | INTEGER | 1 |
| `duration_seconds` | FLOAT NULL | set on resolution |

**Deduplication**: at most one incident per (`endpoint_id`, `rule_id`) in
`open`/`acknowledged` state; recurrences bump `occurrences` and `last_seen_at`.

### 2.6 `alerts` — notification attempts (delivery proof)

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `incident_id` | INTEGER NULL FK → `incidents.id` | `NULL` for channel test alerts |
| `created_at` | DATETIME | indexed |
| `channel` | VARCHAR(20) | `slack` / `email` / `call` / `log` |
| `destination` | VARCHAR(255) | channel label, e-mail address, phone number or `DRY-RUN (…)` |
| `subject` | VARCHAR(255) | |
| `body` | TEXT | e-mail body / Slack block summary / call script |
| `payload` | JSON | **exact provider payload** (Slack blocks, SMTP envelope, Twilio request) |
| `status` | VARCHAR(20) | `sent` / `failed` / `simulated` |
| `delivery_note` | TEXT | provider response or dry-run explanation |
| `severity` | VARCHAR(20) | copied from the incident |

### 2.7 `settings_kv` — runtime configuration

| Column | Type | Notes |
|---|---|---|
| `key` | VARCHAR(80) PK | e.g. `latency_threshold_ms`, `slack_webhook_url`, `live_eval_last_id` |
| `value` | TEXT | |
| `updated_at` | DATETIME | |

`live_eval_last_id` is an internal cursor used by the live-traffic evaluator so
each request log is evaluated exactly once.

---

## 3. Indexes

| Table | Index | Purpose |
|---|---|---|
| `endpoints` | `UNIQUE(method, path)` | catalogue integrity |
| `checks` | `endpoint_id`, `checked_at`, `ok` | windowed aggregations, uptime strips |
| `request_logs` | `ts`, `path`, `status_code`, `is_error`, `request_id` | traffic analytics, live detection |
| `error_logs` | `ts`, `path`, `request_id` | RCA evidence lookup |
| `incidents` | `public_id` (unique), `rule_id`, `status`, `detected_at` | console filters |
| `alerts` | `incident_id`, `created_at`, `channel` | feed and proof |

---

## 4. Data volume & retention

| Table | Rows/day (defaults) | Retention policy |
|---|---|---|
| `checks` | ≈ 34 500 (4 endpoints × 10 s) | 72 h rolling (cleanup job candidate) |
| `request_logs` | traffic-dependent (demo seed ≈ 16 000/24 h) | 72 h rolling |
| `error_logs` | failure-dependent | 30 days (evidence) |
| `incidents` / `alerts` | low volume | keep indefinitely (audit trail) |

Retention helper (SQLite):

```sql
DELETE FROM checks       WHERE checked_at < datetime('now', '-72 hours');
DELETE FROM request_logs WHERE ts         < datetime('now', '-72 hours');
DELETE FROM error_logs   WHERE ts         < datetime('now', '-30 days');
VACUUM;
```

## 5. Migrating to PostgreSQL

1. Set `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/apiguard`.
2. `pip install psycopg[binary]`.
3. Replace the SQLite bucket expression in `app/monitoring/analytics.py`:
   ```python
   # SQLite
   cast(func.strftime("%s", Check.checked_at), Integer) / bucket_seconds
   # PostgreSQL
   func.floor(func.extract("epoch", Check.checked_at) / bucket_seconds)
   ```
4. Everything else (models, JSON columns, naive-UTC timestamps) is portable.

## 6. Sample queries

```sql
-- 24h uptime per endpoint
SELECT e.path,
       ROUND(100.0 * SUM(CASE WHEN c.ok THEN 1 ELSE 0 END) / COUNT(*), 3) AS uptime_pct,
       ROUND(AVG(c.latency_ms), 2)                                        AS avg_ms
FROM checks c JOIN endpoints e ON e.id = c.endpoint_id
WHERE c.checked_at >= datetime('now', '-24 hours')
GROUP BY e.path;

-- top failing paths in the last hour (real traffic)
SELECT path, status_code, COUNT(*) AS n
FROM request_logs
WHERE ts >= datetime('now', '-1 hour') AND is_error = 1
GROUP BY path, status_code
ORDER BY n DESC;

-- open incidents with their RCA owner
SELECT public_id, rule_id, severity, endpoint_path, owner_team, occurrences, detected_at
FROM incidents
WHERE status IN ('open','acknowledged')
ORDER BY detected_at DESC;

-- alert delivery proof for an incident
SELECT channel, destination, status, delivery_note, created_at
FROM alerts WHERE incident_id = (SELECT id FROM incidents WHERE public_id = 'INC-20261101-XXXXXX')
ORDER BY id;
```
