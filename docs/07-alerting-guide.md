# Alerting Guide — rules, channels and notification proof

## 1. Alert rule catalogue

| Rule | Trigger condition | Severity | Channels | Auto-resolve |
|---|---|---|---|---|
| `API_DOWN` | `DOWNTIME_CONSECUTIVE_FAILURES` (2) consecutive probe failures **or** a transport error (connection refused / DNS) | critical | Slack + Email + **Call** | after 2 consecutive successful probes |
| `SERVER_ERROR` | HTTP 5xx on any monitored endpoint or live request | critical | Slack + Email + **Call** | 2 successes |
| `TIMEOUT` | Request exceeds the timeout budget, HTTP 408/504, or the client aborts | critical | Slack + Email + **Call** | 2 successes |
| `HEALTH_CHECK_FAILED` | `/health` returns non-200 / reports unhealthy | critical | Slack + Email + **Call** | 2 successes |
| `SLOW_RESPONSE` | Latency > `LATENCY_THRESHOLD_MS` (3000 ms) and no timeout was recorded | warning | Slack + Email | 2 successes |
| `HIGH_ERROR_RATE` | Failure rate > `ERROR_RATE_THRESHOLD_PCT` (5 %) over `ERROR_RATE_WINDOW_MINUTES` (5 min), min. 3 samples | warning | Slack + Email | 2 successes |
| `AUTH_FAILURE` | HTTP 401 / 403 | warning | Slack + Email | 2 successes |
| `RATE_LIMIT` | HTTP 429 | warning | Slack + Email | 2 successes |
| `CLIENT_ERROR` | Other HTTP 4xx observed on live traffic | info | Slack + Email | 2 successes |

**Fallback:** any open incident that has not re-occurred for
`STALE_INCIDENT_MINUTES` (15 min) is resolved automatically — a rule that is
still failing updates `last_seen_at` on every probe cycle.

### Rule evaluation order
`SERVER_ERROR` → `TIMEOUT` → `AUTH_FAILURE` → `RATE_LIMIT` → `API_DOWN` →
`SLOW_RESPONSE` (suppressed when a timeout fired) → `HIGH_ERROR_RATE` →
`HEALTH_CHECK_FAILED`.

## 2. Incident lifecycle

```
detected ──► open ──► acknowledged ──► resolved
   │           ▲                          ▲
   │           │  recurrence bumps        │  2 consecutive healthy probes
   └── RCA ────┘  occurrences +           │  or manual resolve
       evidence       last_seen_at        │  or 15 min silent (sweeper)
       alerts
```

- **De-duplication**: one open incident per (`endpoint`, `rule`).
- **Cooldown**: notifications are re-sent at most once per
  `ALERT_COOLDOWN_SECONDS` (60 s) per incident.
- **Escalation**: critical incidents add the voice-call channel.

## 3. Notification channels

| Channel | Transport | Configuration | Dry-run behaviour |
|---|---|---|---|
| **Slack** | incoming webhook (`chat.postMessage` payload with Block Kit) | `SLACK_WEBHOOK_URL`, `SLACK_CHANNEL_LABEL` | payload rendered and stored, `status=simulated` |
| **Email** | SMTP (STARTTLS, optional auth) | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO` | subject + body rendered and stored |
| **Phone call** | Twilio `Calls` API with a TwiML `<Say>` script (critical only) | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `ALERT_CALL_TO_NUMBER` | call script rendered and stored |
| **Outbox** | local files | always on | `data/alert-outbox/alerts-<date>.jsonl` + `alerts.log` |

Every dispatch — real or dry-run — creates an `alerts` row with:

```json
{
  "channel": "slack",
  "destination": "#api-alerts (DRY-RUN)",
  "status": "simulated",
  "delivery_note": "SLACK_WEBHOOK_URL not configured - rendered payload stored as DRY-RUN proof.",
  "payload": { "channel": "#api-alerts", "attachments": [ { "blocks": [ ... ] } ] }
}
```

### Enabling live delivery

**Slack**
1. Create an app → *Incoming Webhooks* → add a webhook for `#api-alerts`.
2. `SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T000/B000/XXXX` in `.env`
   (or Settings → Notification channels in the UI).
3. Restart, then press **Send test alert** on the Alerts page.

**Email (Gmail example)**
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=<app password>
ALERT_EMAIL_FROM=you@gmail.com
ALERT_EMAIL_TO=sre-oncall@example.com
```

**Twilio voice call**
```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_FROM_NUMBER=+15550000000
ALERT_CALL_TO_NUMBER=+919999999999
```

Runtime changes are accepted without a restart:
```bash
curl -X PUT localhost:8000/monitor/settings \
  -H 'Content-Type: application/json' \
  -d '{"slack_webhook_url":"https://hooks.slack.com/services/…","alert_email_to":"sre@company.com"}'
```

## 4. Alert content

**Slack** — Block Kit message: header with severity + title, incident fields
(id, rule, endpoint, status, occurrences, detection time), *Root cause*,
*Evidence*, *Recommended actions*, and a context line with owner, confidence and
a link to the incident.

**Email** — plain-text report:

```
Subject: [CRITICAL] SERVER_ERROR on /simulate-error (INC-20261101-D6549F)

Incident ID : INC-20261101-D6549F
Rule        : SERVER_ERROR (HTTP 5xx server error)
Severity    : CRITICAL
Endpoint    : /simulate-error
HTTP status : 500
Detected at : 2026-11-01 17:24:41 UTC

ROOT CAUSE (confidence: high)
  Unhandled RuntimeError raised while serving GET /simulate-error: …

PROBABLE CAUSES / EVIDENCE / RECOMMENDED ACTIONS / OWNER TEAM
```

**Phone call** — TwiML `<Say>`: severity, title, endpoint, one-line root cause
and the incident id, asking the recipient to acknowledge in the dashboard.

## 5. Testing alerts

| Action | How |
|---|---|
| Single channel | Alerts page → **Send test alert** on a channel card |
| All channels | Alerts page → **Test all channels** |
| API | `curl -X POST "localhost:8000/monitor/notifications/test?channels=slack,email,call"` |
| End-to-end | Failure Lab → run `server_error` (critical ⇒ also triggers the call channel) |

The test alert uses `public_id = TEST-XXXXXX`, `rule_id = TEST` and does **not**
create a real incident.

## 6. Notification proof (what to attach to a report)

1. **Dashboard** → Alerts → click **payload** on any row → exact provider payload.
2. **Outbox files** → `backend/data/alert-outbox/alerts-<date>.jsonl` (machine
   readable) and `alerts.log` (human readable).
3. **API** → `GET /monitor/alerts?limit=100` and `GET /monitor/alerts/outbox`.
4. **Database** →
   ```sql
   SELECT created_at, channel, destination, status, delivery_note
   FROM alerts ORDER BY id DESC LIMIT 20;
   ```

Example outbox line (dry-run):

```json
{"created_at":"2026-11-01T17:24:41.512345+00:00","channel":"slack","status":"simulated",
 "destination":"DRY-RUN (no webhook set)","severity":"critical",
 "subject":"HTTP 5xx server error on /simulate-error",
 "incident_public_id":"INC-20261101-D6549F","rule_id":"SERVER_ERROR",
 "delivery_note":"Triggered by rule SERVER_ERROR (failure-lab detection). SLACK_WEBHOOK_URL not configured - rendered payload stored as DRY-RUN proof.",
 "payload":{"channel":"#api-alerts","attachments":[{"color":"#E5484D","blocks":[…]}]}}
```

## 7. Tuning recommendations

| Symptom | Change |
|---|---|
| Alert fatigue from a flapping endpoint | raise `DOWNTIME_CONSECUTIVE_FAILURES`, raise `ALERT_COOLDOWN_SECONDS` |
| Slow degradation never alerts | lower `LATENCY_THRESHOLD_MS` (e.g. 1500) |
| Noisy warning alerts | raise `ERROR_RATE_THRESHOLD_PCT` or shorten `ERROR_RATE_WINDOW_MINUTES` |
| Incidents resolve too fast | raise `RECOVERY_CONSECUTIVE_SUCCESSES` |
| Probe load too high | raise `PROBE_INTERVAL_SECONDS` (30 s is usually enough) |
