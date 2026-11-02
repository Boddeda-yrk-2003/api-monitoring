"""
Database schema for APIGuard (SQLite / PostgreSQL compatible).

Tables
------
endpoints      - catalogue of monitored API endpoints
checks         - every synthetic probe result (availability + latency)
request_logs   - real inbound HTTP traffic recorded by middleware
error_logs     - captured exceptions w/ traceback (root cause evidence)
incidents      - deduplicated failures with RCA attached
alerts         - every notification attempt (Slack / Email / Call / outbox)
settings_kv    - runtime tunable thresholds & notification config
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    """Naive UTC timestamp - stored consistently across SQLite/Postgres."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Endpoint(Base):
    __tablename__ = "endpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(10), default="GET")
    description: Mapped[str] = mapped_column(Text, default="")
    group_name: Mapped[str] = mapped_column(String(60), default="core")
    expected_status: Mapped[int] = mapped_column(Integer, default=200)
    latency_threshold_ms: Mapped[float] = mapped_column(Float, default=3000.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    criticality: Mapped[str] = mapped_column(String(20), default="medium")  # low/med/high/critical
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    checks: Mapped[list["Check"]] = relationship(back_populates="endpoint", cascade="all,delete-orphan")
    incidents: Mapped[list["Incident"]] = relationship(back_populates="endpoint", cascade="all,delete-orphan")

    __table_args__ = (UniqueConstraint("method", "path", name="uq_endpoint_method_path"),)


class Check(Base):
    """One synthetic probe execution."""
    __tablename__ = "checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("endpoints.id"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error_type: Mapped[str] = mapped_column(String(40), default="none")  # none|timeout|connection|http_error
    error_message: Mapped[str] = mapped_column(Text, default="")
    request_id: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(20), default="synthetic")  # synthetic|live

    endpoint: Mapped["Endpoint"] = relationship(back_populates="checks")


class RequestLog(Base):
    """Real inbound traffic (captured by the RequestContextMiddleware)."""
    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    method: Mapped[str] = mapped_column(String(10), default="GET")
    path: Mapped[str] = mapped_column(String(255), index=True)
    status_code: Mapped[int] = mapped_column(Integer, default=200, index=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    request_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    client_ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    is_error: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class ErrorLog(Base):
    """Captured server exception - primary evidence for root cause analysis."""
    __tablename__ = "error_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    request_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    method: Mapped[str] = mapped_column(String(10), default="GET")
    path: Mapped[str] = mapped_column(String(255), index=True)
    exception_type: Mapped[str] = mapped_column(String(120), default="")
    exception_message: Mapped[str] = mapped_column(Text, default="")
    traceback: Mapped[str] = mapped_column(Text, default="")
    status_code: Mapped[int] = mapped_column(Integer, default=500)
    client_ip: Mapped[str] = mapped_column(String(64), default="")
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)


class Incident(Base):
    """A deduplicated failure with root-cause analysis attached."""
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    endpoint_id: Mapped[int | None] = mapped_column(ForeignKey("endpoints.id"), nullable=True)
    rule_id: Mapped[str] = mapped_column(String(60), index=True)          # e.g. SERVER_ERROR
    title: Mapped[str] = mapped_column(String(255), default="")
    severity: Mapped[str] = mapped_column(String(20), default="warning")  # info|warning|critical
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open|acknowledged|resolved
    category: Mapped[str] = mapped_column(String(40), default="")   # auth|timeout|server_error|rate_limit|...

    endpoint_path: Mapped[str] = mapped_column(String(255), default="")
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_type: Mapped[str] = mapped_column(String(40), default="")

    # ---- root cause analysis block
    root_cause: Mapped[str] = mapped_column(Text, default="")
    root_cause_confidence: Mapped[str] = mapped_column(String(20), default="medium")
    probable_causes: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    recommended_actions: Mapped[list] = mapped_column(JSON, default=list)
    owner_team: Mapped[str] = mapped_column(String(80), default="")

    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    endpoint: Mapped["Endpoint | None"] = relationship(back_populates="incidents")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="incident", cascade="all,delete-orphan")


class Alert(Base):
    """A notification attempt for an incident (Slack / Email / Call / outbox)."""
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    channel: Mapped[str] = mapped_column(String(20), default="log")     # slack|email|call|log
    destination: Mapped[str] = mapped_column(String(255), default="")
    subject: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)            # exact provider payload
    status: Mapped[str] = mapped_column(String(20), default="simulated") # sent|failed|simulated
    delivery_note: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20), default="warning")

    incident: Mapped["Incident | None"] = relationship(back_populates="alerts")


class SettingKV(Base):
    """Runtime tunable configuration (thresholds + notification channels)."""
    __tablename__ = "settings_kv"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
