# Alert Notification Proof

Every alert dispatched by APIGuard is persisted with the **exact provider payload**.
This document is generated from the running system and the local alert outbox.

| Metric | Value |
|---|---|
| Alert records (database `alerts`) | **35** |
| Outbox records (`data/alert-outbox/*.jsonl`) | **23** |
| Channels | email (14), slack (14), call (7) |
| Delivery status | simulated (35) |
| Severity mix | critical (21), warning (14) |
| Incidents with RCA | 14 |
| Outbox path | `/home/user/api-monitoring/backend/data/alert-outbox` |

> **Why `simulated`?** No Slack webhook / SMTP / Twilio credentials are configured in the demo
> environment. APIGuard still renders the complete payload and stores it with status
> `simulated` — i.e. this file *is* the delivery proof. Configure credentials (see
> `docs/07-alerting-guide.md`) and the status flips to `sent`.

## 1. Delivery log (most recent 25)

| Time (UTC) | Channel | Destination | Severity | Status | Subject |
|---|---|---|---|---|---|
| 2026-11-01T17:50:28.601595 | call | DRY-RUN (no Twilio set) | critical | **simulated** | Voice call - HTTP 5xx server error on /health |
| 2026-11-01T17:50:28.601135 | email | DRY-RUN (no SMTP set) | critical | **simulated** | [CRITICAL] SERVER_ERROR on /health (INC-20261101-3E133C) |
| 2026-11-01T17:50:28.600573 | slack | DRY-RUN (no webhook set) | critical | **simulated** | HTTP 5xx server error on /health |
| 2026-11-01T17:50:27.515304 | call | DRY-RUN (no Twilio set) | critical | **simulated** | Voice call - API endpoint unavailable on http://127.0.0.1:9/health |
| 2026-11-01T17:50:27.514786 | email | DRY-RUN (no SMTP set) | critical | **simulated** | [CRITICAL] API_DOWN on http://127.0.0.1:9/health (INC-20261101-3EE8EC) |
| 2026-11-01T17:50:27.514198 | slack | DRY-RUN (no webhook set) | critical | **simulated** | API endpoint unavailable on http://127.0.0.1:9/health |
| 2026-11-01T17:50:26.493696 | call | DRY-RUN (no Twilio set) | critical | **simulated** | Voice call - Service health check failed on /health |
| 2026-11-01T17:50:26.493240 | email | DRY-RUN (no SMTP set) | critical | **simulated** | [CRITICAL] HEALTH_CHECK_FAILED on /health (INC-20261101-077933) |
| 2026-11-01T17:50:26.492676 | slack | DRY-RUN (no webhook set) | critical | **simulated** | Service health check failed on /health |
| 2026-11-01T17:50:25.470459 | email | DRY-RUN (no SMTP set) | warning | **simulated** | [WARNING] SLOW_RESPONSE on /simulate-timeout (INC-20261101-0EFEE2) |
| 2026-11-01T17:50:25.469843 | slack | DRY-RUN (no webhook set) | warning | **simulated** | Response time above SLO on /simulate-timeout |
| 2026-11-01T17:50:20.947289 | email | DRY-RUN (no SMTP set) | warning | **simulated** | [WARNING] RATE_LIMIT on /simulate-rate-limit (INC-20261101-B06041) |
| 2026-11-01T17:50:20.946647 | slack | DRY-RUN (no webhook set) | warning | **simulated** | Rate limit exceeded (HTTP 429) on /simulate-rate-limit |
| 2026-11-01T17:50:19.909937 | call | DRY-RUN (no Twilio set) | critical | **simulated** | Voice call - HTTP 5xx server error on /simulate-error |
| 2026-11-01T17:50:19.909503 | email | DRY-RUN (no SMTP set) | critical | **simulated** | [CRITICAL] SERVER_ERROR on /simulate-error (INC-20261101-98052D) |
| 2026-11-01T17:50:19.908873 | slack | DRY-RUN (no webhook set) | critical | **simulated** | HTTP 5xx server error on /simulate-error |
| 2026-11-01T17:50:18.885597 | call | DRY-RUN (no Twilio set) | critical | **simulated** | Voice call - Request timeout on /simulate-timeout |
| 2026-11-01T17:50:18.885085 | email | DRY-RUN (no SMTP set) | critical | **simulated** | [CRITICAL] TIMEOUT on /simulate-timeout (INC-20261101-FBB3D9) |
| 2026-11-01T17:50:18.884532 | slack | DRY-RUN (no webhook set) | critical | **simulated** | Request timeout on /simulate-timeout |
| 2026-11-01T17:50:18.558447 | email | DRY-RUN (no SMTP set) | warning | **simulated** | [WARNING] AUTH_FAILURE on /secure-data (INC-20261101-94171E) |
| 2026-11-01T17:50:18.557858 | slack | DRY-RUN (no webhook set) | warning | **simulated** | Authentication / authorization failure on /secure-data |
| 2026-11-01T17:50:09.859755 | email | DRY-RUN (no SMTP set) | warning | **simulated** | [WARNING] AUTH_FAILURE on /secure-data (INC-20261101-5D8FD7) |
| 2026-11-01T17:50:09.858974 | slack | DRY-RUN (no webhook set) | warning | **simulated** | Authentication / authorization failure on /secure-data |
| 2026-11-01T16:55:26.795517 | call | +91XXXXXXXXXX (DRY-RUN) | critical | **simulated** | HTTP 5xx server error on /health |
| 2026-11-01T16:55:26.795517 | email | sre-oncall@example.com (DRY-RUN) | critical | **simulated** | HTTP 5xx server error on /health |

## 2. Slack payload (Block Kit)

Incident **HTTP 5xx server error on /health** · destination `DRY-RUN (no webhook set)` · status **simulated**

### Slack message

```json
{
  "channel": "#api-alerts",
  "username": "APIGuard Monitor",
  "icon_emoji": ":shield:",
  "attachments": [
    {
      "color": "#E5484D",
      "blocks": [
        {
          "type": "header",
          "text": {
            "type": "plain_text",
            "text": ":rotating_light: CRITICAL - HTTP 5xx server error on /health"
          }
        },
        {
          "type": "section",
          "fields": [
            {
              "type": "mrkdwn",
              "text": "*Incident*\n`INC-20261101-3E133C`"
            },
            {
              "type": "mrkdwn",
              "text": "*Rule*\n`SERVER_ERROR`"
            },
            {
              "type": "mrkdwn",
              "text": "*Endpoint*\n`/health`"
            },
            {
              "type": "mrkdwn",
              "text": "*Status*\nopen"
            },
            {
              "type": "mrkdwn",
              "text": "*Occurrences*\n1"
            },
            {
              "type": "mrkdwn",
              "text": "*Detected*\n2026-11-01 17:50:28 UTC"
            }
          ]
        },
        {
          "type": "section",
          "text": {
            "type": "mrkdwn",
            "text": "*Root cause*\nUnhandled DependencyUnavailable raised while serving GET /health: Readiness dependency 'cache' failed health probe"
          }
        },
        {
          "type": "section",
          "text": {
            "type": "mrkdwn",
            "text": "*Evidence*\n*http_status*: `503`\n*error_type*: `none`\n*latency_ms*: `1.27`\n*latency_threshold_ms*: `3000.0`\n*exception_type*: `DependencyUnavailable`\n*exception_message*: `Readiness dependency 'cache' failed health probe`"
          }
        },
        {
          "type": "section",
          "text": {
            "type": "mrkdwn",
            "text": "*Recommended actions*\n\u2022 Inspect captured stack trace for request_id=lab-e20d7a947d91 (Dashboard -> Incidents -> Evidence)\n\u2022 Reproduce with the same payload in staging and add a regression test\n\u2022 Add explicit exception handling + structured logging around the failing call\n\u2022 Roll back the last release if the error started immediately after a deploy"
          }
        },
        {
          "type": "context",
          "elements": [
            {
              "type": "mrkdwn",
              "text": "Owner: Backend Engineering | confidence: high | <http://localhost:5173/incidents|Open incident in APIGuard>"
            }
          ]
        }
      ]
    }
  ],
  "text": "CRITICAL HTTP 5xx server error on /health - Unhandled Dependenc
  … (truncated)
```

## 3. E-mail payload

**To:** `DRY-RUN (no SMTP set)` · **Subject:** [CRITICAL] SERVER_ERROR on /health (INC-20261101-3E133C) · status **simulated**

```text
APIGuard automated alert
========================

Incident ID : INC-20261101-3E133C
Rule        : SERVER_ERROR (HTTP 5xx server error on /health)
Severity    : CRITICAL
Status      : open
Endpoint    : /health
HTTP status : 503
Latency     : 1.27 ms
Detected at : 2026-11-01 17:50:28 UTC
Occurrences : 1

ROOT CAUSE (confidence: high)
--------------------------------------------------------
Unhandled DependencyUnavailable raised while serving GET /health: Readiness dependency 'cache' failed health probe

PROBABLE CAUSES
--------------------------------------------------------
  - Unhandled exception in route handler or a downstream dependency call
  - Invalid assumption about input data (None / missing key / type mismatch)
  - Downstream service or database returned an error that was not caught
  - Recent deployment introduced a regression (check last deploy diff)

EVIDENCE
--------------------------------------------------------
  - http_status: 503
  - error_type: none
  - latency_ms: 1.27
  - latency_threshold_ms: 3000.0
  - path: /health
  - method: GET
  - request_id: lab-e20d7a947d91
  - transport_error: live traffic failure on /health
  - exception_type: DependencyUnavailable
  - exception_message: Readiness dependency 'cache' failed health probe
  - failing_frames: File "app/routers/sample.py", line 118, in health
  - captured_at: 2026-11-01T16:55:26.795517
  - source: live
  - detection_time_utc: 2026-11-01T17:50:28.597971
  - rule: The API returned a 5xx status code (unhandled server exception).

RECOMMENDED ACTIONS
--------------------------------------------------------
  - Inspect captured stack trace for request_id=lab-e20d7a947d91 (Dashboard -> Incidents -> Evidence)
  - Reproduce with the same payload in staging and add a regression test
  - Add explicit exception handling + structured logging around the failing call
  - Roll back the last release if the error started immediately after a deploy

OWNER TEAM
--------------------------------------------------------
Backend Engineering

-- APIGuard monitoring service (development)
```

## 4. Voice-call payload (critical only)

**To:** `DRY-RUN (no Twilio set)` · status **simulated**

```text
This is an APIGuard critical alert. critical severity. HTTP 5xx server error on /health. Endpoint /health. Root cause: Unhandled DependencyUnavailable raised while serving GET /health: Readiness dependency 'cache' failed health probe. Incident INC-20261101-3E133C. Please acknowledge in the dashboard.
```

Twilio request that would be issued:

### Twilio payload

```json
{
  "to": "DRY-RUN (no Twilio set)",
  "script": "This is an APIGuard critical alert. critical severity. HTTP 5xx server error on /health. Endpoint /health. Root cause: Unhandled DependencyUnavailable raised while serving GET /health: Readiness dependency 'cache' failed health probe. Incident INC-20261101-3E133C. Please acknowledge in the dashboard."
}
```

## 5. Raw outbox (machine readable)
```json
{
  "created_at": "2026-11-01T17:50:28.601595",
  "channel": "call",
  "status": "simulated",
  "destination": "DRY-RUN (no Twilio set)",
  "severity": "critical",
  "subject": "Voice call - HTTP 5xx server error on /health",
  "incident_public_id": "INC-20261101-3E133C",
  "rule_id": "SERVER_ERROR",
  "delivery_note": "Triggered by rule SERVER_ERROR (live detection). Twilio credentials not configured - call script stored as DRY-RUN proof.",
  "payload": {
    "to": "DRY-RUN (no Twilio set)",
    "script": "This is an APIGuard critical alert. critical severity. HTTP 5xx server error on /health. Endpoint /health. Root cause: Unhandled DependencyUnavailable raised while serving GET /health: Readiness dependency 'cache' failed health probe. Incident INC-20261101-3E133C. Please acknowledge in the dashboard."
  }
}
…
{
  "created_at": "2026-11-01T17:50:28.601135",
  "channel": "email",
  "status": "simulated",
  "destination": "DRY-RUN (no SMTP set)",
  "severity": "critical",
  "subject": "[CRITICAL] SERVER_ERROR on /health (INC-20261101-3E133C)",
  "incident_public_id": "INC-20261101-3E133C",
  "rule_id": "SERVER_ERROR",
  "delivery_note": "Triggered by rule SERVER_ERROR (live detection). SMTP not configured - e-mail rendered and stored as DRY-RUN proof.",
  "payload": {
    "to": "DRY-RUN (no SMTP set)",
    "from": "apiguard-alerts@example.com",
    "subject": "[CRITICAL] SERVER_ERROR on /health (INC-20261101-3E133C)",
    "body": "APIGuard automated alert\n========================\n\nIncident ID : INC-20261101-3E133C\nRule        : SERVER_ERROR (HTTP 5xx server error on /health)\nSeverity    : CRITICAL\nStatus      : open\nEndpoint    : /health\nHTTP status : 503\nLatency     : 1.27 ms\nDetected at : 2026-11-01 17:50:28 UTC\nOccurrences : 1\n\nROOT CAUSE (confidence: high)\n--------------------------------------------------------\nUnhandled DependencyUnavailable raised while serving GET /health: Readiness dependency 'cache' failed health probe\n\nPROBABLE CAUSES\n--------------------------
…
{
  "created_at": "2026-11-01T17:50:28.600573",
  "channel": "slack",
  "status": "simulated",
  "destination": "DRY-RUN (no webhook set)",
  "severity": "critical",
  "subject": "HTTP 5xx server error on /health",
  "incident_public_id": "INC-20261101-3E133C",
  "rule_id": "SERVER_ERROR",
  "delivery_note": "Triggered by rule SERVER_ERROR (live detection). SLACK_WEBHOOK_URL not configured - rendered payload stored as DRY-RUN proof.",
  "payload": {
    "channel": "#api-alerts",
    "username": "APIGuard Monitor",
    "icon_emoji": ":shield:",
    "attachments": [
      {
        "color": "#E5484D",
        "blocks": [
          {
            "type": "header",
            "text": {
              "type": "plain_text",
              "text": ":rotating_light: CRITICAL - HTTP 5xx server error on /health"
            }
          },
          {
            "type": "section",
            "fields": [
              {
                "type": "mrkdwn",
                "text": "*Incident*\n`INC-20261101-3E133C`"
              },
              {
                "type": "mrkdwn",
                "text": "*Rule*\n`SERVER_ERROR`"
              },
              {
                "type": "mrkdwn",
 
…
```
## 6. How to verify independently
```bash
# API
curl -s 'http://localhost:8000/monitor/alerts?limit=10' | jq
curl -s 'http://localhost:8000/monitor/alerts/outbox?limit=5' | jq

# Files
cat backend/data/alert-outbox/alerts.log
tail -1 backend/data/alert-outbox/alerts-$(date +%F).jsonl | jq

# Database
sqlite3 backend/data/apiguard.db "SELECT created_at, channel, destination, status FROM alerts ORDER BY id DESC LIMIT 10;"

# Dashboard
#   Alerts view -> click "payload" on any row
```
