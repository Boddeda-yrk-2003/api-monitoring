"""
Central configuration for the APIGuard backend.

All values can be overridden with environment variables or a `.env` file
placed next to this package (see `.env.example`).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]          # -> backend/
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "alert-outbox").mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    # ---------------------------------------------------------------- service
    APP_NAME: str = "APIGuard - API Monitoring Service"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    # Public base URL the monitor uses to probe its own endpoints.
    SELF_BASE_URL: str = "http://127.0.0.1:8000"

    # ------------------------------------------------------------- monitoring
    PROBE_INTERVAL_SECONDS: int = 10       # synthetic check frequency
    REQUEST_TIMEOUT_SECONDS: float = 10.0  # probe timeout budget
    HISTORY_RETENTION_HOURS: int = 72      # rolling cleanup of raw checks
    SEED_HISTORY_ON_STARTUP: bool = True
    SEED_HISTORY_HOURS: int = 24

    # ------------------------------------------------------------ thresholds
    LATENCY_THRESHOLD_MS: float = 3000.0     # alert when p50 latency > 3s
    ERROR_RATE_THRESHOLD_PCT: float = 5.0    # alert when error rate > 5%
    ERROR_RATE_WINDOW_MINUTES: int = 5
    DOWNTIME_CONSECUTIVE_FAILURES: int = 2   # failures before "API down"
    RECOVERY_CONSECUTIVE_SUCCESSES: int = 2  # successes before auto-resolve
    ALERT_COOLDOWN_SECONDS: int = 60         # dedupe window per rule+endpoint
    STALE_INCIDENT_MINUTES: int = 15         # auto-resolve if not seen again
    VALID_API_KEYS: str = "demo-api-key-123,monitoring-key-456"

    # ---------------------------------------------------------- rate limiting
    RATE_LIMIT_MAX_REQUESTS: int = 5
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # ------------------------------------------------------- sample API knobs
    SIMULATED_TIMEOUT_SECONDS: float = 6.0

    # ------------------------------------------------------------- database
    DATABASE_URL: str = f"sqlite:///{DATA_DIR / 'apiguard.db'}"
    ALERT_OUTBOX_DIR: str = str(DATA_DIR / "alert-outbox")

    # -------------------------------------------------------- notifications
    # Slack incoming webhook (leave empty -> alerts are stored as DRY-RUN)
    SLACK_WEBHOOK_URL: str = ""
    SLACK_CHANNEL_LABEL: str = "#api-alerts"

    # Email (SMTP). Leave SMTP_HOST empty -> DRY-RUN (rendered + stored only)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True
    ALERT_EMAIL_FROM: str = "apiguard-alerts@example.com"
    ALERT_EMAIL_TO: str = "sre-oncall@example.com"

    # Optional phone / call alert (Twilio). Empty -> DRY-RUN
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    ALERT_CALL_TO_NUMBER: str = ""

    # ------------------------------------------------------------- security
    CORS_ORIGINS: str = "*"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def valid_api_keys(self) -> set[str]:
        return {k.strip() for k in self.VALID_API_KEYS.split(",") if k.strip()}

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def slack_enabled(self) -> bool:
        return bool(self.SLACK_WEBHOOK_URL.strip())

    @property
    def email_enabled(self) -> bool:
        return bool(self.SMTP_HOST.strip() and self.ALERT_EMAIL_TO.strip())

    @property
    def call_enabled(self) -> bool:
        return all(
            [
                self.TWILIO_ACCOUNT_SID.strip(),
                self.TWILIO_AUTH_TOKEN.strip(),
                self.TWILIO_FROM_NUMBER.strip(),
                self.ALERT_CALL_TO_NUMBER.strip(),
            ]
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
