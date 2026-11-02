"""
Notification layer.

Three real channels are supported (Slack webhook, SMTP e-mail, Twilio voice
call). When a channel is not configured with credentials the alert is still
fully rendered and stored with status="simulated" (DRY-RUN) - this keeps the
demo runnable offline while producing verifiable notification proof.

Every dispatch also lands in the local outbox:
    backend/data/alert-outbox/alerts-YYYY-MM-DD.jsonl   (machine readable)
    backend/data/alert-outbox/alerts.log                (human readable)
"""
from __future__ import annotations

import json
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Iterable

import httpx
from sqlalchemy.orm import Session

from app.core.config import DATA_DIR, settings
from app.models import Alert, Incident

OUTBOX_DIR: Path = Path(settings.ALERT_OUTBOX_DIR)
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

SEVERITY_EMOJI = {"critical": ":rotating_light:", "warning": ":warning:", "info": ":information_source:"}
SEVERITY_COLOR = {"critical": "#E5484D", "warning": "#F5A524", "info": "#3E63DD"}


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _evidence_lines(incident: Incident, limit: int = 6) -> list[str]:
    ev = incident.evidence or {}
    keys = [
        "http_status",
        "error_type",
        "latency_ms",
        "latency_threshold_ms",
        "exception_type",
        "exception_message",
        "failing_frames",
        "request_id",
        "error_rate_pct",
        "transport_error",
    ]
    lines = []
    for k in keys:
        if k in ev and ev[k] not in (None, "", []):
            value = str(ev[k])
            lines.append(f"*{k}*: `{value[:220]}`")
        if len(lines) >= limit:
            break
    return lines or ["_no structured evidence captured_"]


def render_slack_payload(incident: Incident, dashboard_url: str = "http://localhost:5173/incidents") -> dict[str, Any]:
    emoji = SEVERITY_EMOJI.get(incident.severity, ":warning:")
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {incident.severity.upper()} - {incident.title}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Incident*\n`{incident.public_id}`"},
                {"type": "mrkdwn", "text": f"*Rule*\n`{incident.rule_id}`"},
                {"type": "mrkdwn", "text": f"*Endpoint*\n`{incident.endpoint_path}`"},
                {"type": "mrkdwn", "text": f"*Status*\n{incident.status}"},
                {"type": "mrkdwn", "text": f"*Occurrences*\n{incident.occurrences}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Detected*\n{incident.detected_at.strftime('%Y-%m-%d %H:%M:%S')} UTC",
                },
            ],
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Root cause*\n{incident.root_cause}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Evidence*\n" + "\n".join(_evidence_lines(incident))}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Recommended actions*\n"
                + "\n".join(f"• {a}" for a in (incident.recommended_actions or [])[:5]),
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Owner: {incident.owner_team} | confidence: {incident.root_cause_confidence} | "
                    f"<{dashboard_url}|Open incident in APIGuard>",
                }
            ],
        },
    ]
    return {
        "channel": settings.SLACK_CHANNEL_LABEL,
        "username": "APIGuard Monitor",
        "icon_emoji": ":shield:",
        "attachments": [{"color": SEVERITY_COLOR.get(incident.severity, "#F5A524"), "blocks": blocks}],
        "text": f"{incident.severity.upper()} {incident.title} - {incident.root_cause}",
    }


def render_email(incident: Incident) -> tuple[str, str]:
    subject = (
        f"[{incident.severity.upper()}] {incident.rule_id} on {incident.endpoint_path} "
        f"({incident.public_id})"
    )
    actions = "\n".join(f"  - {a}" for a in (incident.recommended_actions or [])) or "  - n/a"
    causes = "\n".join(f"  - {c}" for c in (incident.probable_causes or [])) or "  - n/a"
    evidence = "\n".join(
        f"  - {k}: {str(v)[:200]}" for k, v in (incident.evidence or {}).items() if k != "traceback"
    ) or "  - n/a"
    body = f"""
APIGuard automated alert
========================

Incident ID : {incident.public_id}
Rule        : {incident.rule_id} ({incident.title})
Severity    : {incident.severity.upper()}
Status      : {incident.status}
Endpoint    : {incident.endpoint_path}
HTTP status : {incident.http_status}
Latency     : {incident.latency_ms if incident.latency_ms is not None else '-'} ms
Detected at : {incident.detected_at.strftime('%Y-%m-%d %H:%M:%S')} UTC
Occurrences : {incident.occurrences}

ROOT CAUSE (confidence: {incident.root_cause_confidence})
--------------------------------------------------------
{incident.root_cause}

PROBABLE CAUSES
--------------------------------------------------------
{causes}

EVIDENCE
--------------------------------------------------------
{evidence}

RECOMMENDED ACTIONS
--------------------------------------------------------
{actions}

OWNER TEAM
--------------------------------------------------------
{incident.owner_team}

-- APIGuard monitoring service ({settings.ENVIRONMENT})
"""
    return subject, body.strip()


def render_call_script(incident: Incident) -> str:
    return (
        f"This is an APIGuard critical alert. {incident.severity} severity. "
        f"{incident.title}. Endpoint {incident.endpoint_path}. "
        f"Root cause: {incident.root_cause[:200]}. "
        f"Incident {incident.public_id}. Please acknowledge in the dashboard."
    )


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #
def _send_slack(payload: dict[str, Any]) -> tuple[str, str]:
    if not settings.slack_enabled:
        return "simulated", "SLACK_WEBHOOK_URL not configured - rendered payload stored as DRY-RUN proof."
    try:
        r = httpx.post(settings.SLACK_WEBHOOK_URL, json=payload, timeout=8.0)
        if 200 <= r.status_code < 300:
            return "sent", f"Slack accepted the message (HTTP {r.status_code})."
        return "failed", f"Slack returned HTTP {r.status_code}: {r.text[:200]}"
    except Exception as exc:  # pragma: no cover - network failure path
        return "failed", f"Slack delivery error: {exc}"


def _send_email(subject: str, body: str) -> tuple[str, str]:
    if not settings.email_enabled:
        return "simulated", "SMTP not configured - e-mail rendered and stored as DRY-RUN proof."
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.ALERT_EMAIL_FROM
    msg["To"] = settings.ALERT_EMAIL_TO
    msg.set_content(body)
    try:  # pragma: no cover - requires real SMTP server
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_STARTTLS:
                server.starttls()
            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
        return "sent", f"E-mail delivered to {settings.ALERT_EMAIL_TO} via {settings.SMTP_HOST}."
    except Exception as exc:
        return "failed", f"SMTP delivery error: {exc}"


def _send_call(incident: Incident) -> tuple[str, str]:
    if not settings.call_enabled:
        return "simulated", "Twilio credentials not configured - call script stored as DRY-RUN proof."
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Calls.json"
    data = {
        "To": settings.ALERT_CALL_TO_NUMBER,
        "From": settings.TWILIO_FROM_NUMBER,
        "Twiml": f"<Response><Say voice='alice'>{render_call_script(incident)}</Say></Response>",
    }
    try:  # pragma: no cover - requires Twilio account
        r = httpx.post(url, data=data, auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN), timeout=10)
        if 200 <= r.status_code < 300:
            return "sent", f"Call placed to {settings.ALERT_CALL_TO_NUMBER} (sid {r.json().get('sid')})."
        return "failed", f"Twilio returned HTTP {r.status_code}: {r.text[:200]}"
    except Exception as exc:
        return "failed", f"Twilio delivery error: {exc}"


# --------------------------------------------------------------------------- #
# Outbox (always-on proof)
# --------------------------------------------------------------------------- #
def _write_outbox(record: dict[str, Any]) -> None:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with (OUTBOX_DIR / f"alerts-{day}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
    with (OUTBOX_DIR / "alerts.log").open("a", encoding="utf-8") as fh:
        fh.write(
            f"[{record['created_at']}] {record['channel'].upper():5s} {record['status']:9s} "
            f"{record['incident_public_id']} {record['severity'].upper():8s} {record['subject']}\n"
        )


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #
def dispatch(
    db: Session,
    incident: Incident,
    channels: Iterable[str] | None = None,
    note: str = "",
) -> list[Alert]:
    """Render + deliver + persist an alert on every requested channel."""
    channels = list(channels) if channels else ["slack", "email"]
    created: list[Alert] = []

    subject, body = render_email(incident)
    slack_payload = render_slack_payload(incident)

    for channel in channels:
        if channel == "slack":
            status, note_txt = _send_slack(slack_payload)
            destination = settings.SLACK_CHANNEL_LABEL if settings.slack_enabled else "DRY-RUN (no webhook set)"
            payload = slack_payload
            subject_txt = incident.title
            body_txt = json.dumps(slack_payload.get("attachments", [{}])[0], indent=2, default=str)[:4000]
        elif channel == "email":
            status, note_txt = _send_email(subject, body)
            destination = settings.ALERT_EMAIL_TO if settings.email_enabled else "DRY-RUN (no SMTP set)"
            payload = {"to": destination, "from": settings.ALERT_EMAIL_FROM, "subject": subject, "body": body}
            subject_txt, body_txt = subject, body
        elif channel == "call":
            status, note_txt = _send_call(incident)
            destination = settings.ALERT_CALL_TO_NUMBER if settings.call_enabled else "DRY-RUN (no Twilio set)"
            payload = {"to": destination, "script": render_call_script(incident)}
            subject_txt = f"Voice call - {incident.title}"
            body_txt = render_call_script(incident)
        else:  # log / outbox only
            status, note_txt = "simulated", "Stored in local alert outbox."
            destination = "local-outbox"
            payload = {"incident": incident.public_id}
            subject_txt, body_txt = subject, body

        alert = Alert(
            incident_id=incident.id,
            channel=channel,
            destination=destination,
            subject=subject_txt,
            body=body_txt,
            payload=payload,
            status=status,
            delivery_note=(note + " " + note_txt).strip(),
            severity=incident.severity,
        )
        db.add(alert)
        db.flush()
        created.append(alert)

        _write_outbox(
            {
                "created_at": alert.created_at.isoformat() if alert.created_at else datetime.now(timezone.utc).isoformat(),
                "channel": channel,
                "status": status,
                "destination": destination,
                "severity": incident.severity,
                "subject": subject_txt,
                "incident_public_id": incident.public_id,
                "rule_id": incident.rule_id,
                "delivery_note": alert.delivery_note,
                "payload": payload,
            }
        )
    db.commit()
    return created
