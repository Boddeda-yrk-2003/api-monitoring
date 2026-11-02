"""Pydantic v2 schemas (request/response contracts for the monitoring API)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------- health
class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    timestamp: datetime
    uptime_seconds: float
    database: str
    checks_recorded: int


# ---------------------------------------------------------------- sample data
class User(BaseModel):
    id: int
    name: str
    email: str
    role: str
    active: bool


class Product(BaseModel):
    id: int
    sku: str
    name: str
    category: str
    price: float
    stock: int


# ------------------------------------------------------------------- monitor
class EndpointOut(BaseModel):
    id: int
    name: str
    path: str
    method: str
    description: str = ""
    group_name: str = "core"
    expected_status: int = 200
    latency_threshold_ms: float = 3000.0
    enabled: bool = True
    criticality: str = "medium"

    model_config = {"from_attributes": True}


class EndpointStats(BaseModel):
    id: int
    name: str
    path: str
    method: str
    group_name: str = "core"
    criticality: str = "medium"
    status: str = "unknown"                  # healthy|degraded|down|unknown
    uptime_pct: float = 100.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    total_checks: int = 0
    failed_checks: int = 0
    error_rate_pct: float = 0.0
    last_status_code: int | None = None
    last_checked_at: datetime | None = None
    last_error: str = ""
    open_incidents: int = 0
    sparkline: list[float] = Field(default_factory=list)


class SummaryOut(BaseModel):
    status: str = "healthy"
    uptime_pct: float = 100.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    total_requests: int = 0
    failed_requests: int = 0
    error_rate_pct: float = 0.0
    total_checks: int = 0
    open_incidents: int = 0
    critical_incidents: int = 0
    alerts_last_24h: int = 0
    endpoints_monitored: int = 0
    endpoints_up: int = 0
    endpoints_down: int = 0
    endpoints_degraded: int = 0
    max_latency_ms: float = 0.0
    check_error_rate_pct: float = 0.0
    window: str = "24h"
    generated_at: datetime
    monitor_running: bool = True


class TimeSeriesPoint(BaseModel):
    bucket: str
    total: int = 0
    success: int = 0
    failed: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    error_rate_pct: float = 0.0


class StatusBreakdown(BaseModel):
    status_code: int
    count: int
    label: str = ""


class IncidentOut(BaseModel):
    id: int
    public_id: str
    endpoint_path: str = ""
    rule_id: str = ""
    title: str = ""
    severity: str = "warning"
    status: str = "open"
    category: str = ""
    http_status: int | None = None
    latency_ms: float | None = None
    error_type: str = ""
    root_cause: str = ""
    root_cause_confidence: str = "medium"
    probable_causes: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommended_actions: list[str] = Field(default_factory=list)
    owner_team: str = ""
    detected_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None = None
    occurrences: int = 1
    duration_seconds: float | None = None
    alert_count: int = 0
    channels: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AlertOut(BaseModel):
    id: int
    incident_id: int | None = None
    created_at: datetime
    channel: str
    destination: str = ""
    subject: str = ""
    body: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str = "simulated"
    delivery_note: str = ""
    severity: str = "warning"
    incident_title: str = ""

    model_config = {"from_attributes": True}


class ErrorLogOut(BaseModel):
    id: int
    ts: datetime
    request_id: str = ""
    method: str = ""
    path: str = ""
    exception_type: str = ""
    exception_message: str = ""
    traceback: str = ""
    status_code: int = 500
    latency_ms: float = 0.0

    model_config = {"from_attributes": True}


class CheckOut(BaseModel):
    id: int
    endpoint_id: int
    checked_at: datetime
    ok: bool
    status_code: int | None = None
    latency_ms: float = 0.0
    error_type: str = "none"
    error_message: str = ""
    endpoint_path: str = ""

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ simulation
class SimulationResult(BaseModel):
    scenario: str
    title: str
    endpoint: str
    http_status: int | None = None
    latency_ms: float = 0.0
    expected_detection: str = ""
    detected: bool = False
    detection_latency_ms: float = 0.0
    incident: IncidentOut | None = None
    alerts: list[AlertOut] = Field(default_factory=list)
    message: str = ""
    raw_response: dict[str, Any] = Field(default_factory=dict)


class ChannelTestResult(BaseModel):
    channel: str
    configured: bool
    status: str
    destination: str = ""
    note: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class SettingsOut(BaseModel):
    latency_threshold_ms: float
    error_rate_threshold_pct: float
    error_rate_window_minutes: int
    downtime_consecutive_failures: int
    recovery_consecutive_successes: int
    alert_cooldown_seconds: int
    probe_interval_seconds: int
    rate_limit_max_requests: int
    simulated_timeout_seconds: float
    channels: dict[str, bool]
    channel_targets: dict[str, str]
