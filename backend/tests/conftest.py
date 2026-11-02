"""
Hermetic test bootstrap.

The suite starts its **own** uvicorn instance on a dedicated port with its own
SQLite file and alert outbox, so running `pytest` never touches the database or
the notification history of a running development server.

Environment per test session
----------------------------
    DATABASE_URL        backend/data/apiguard_test.db   (recreated)
    ALERT_OUTBOX_DIR    backend/data/test-outbox
    SELF_BASE_URL       http://127.0.0.1:8123           (the test server)
    PROBE_INTERVAL      3600 s  (the loop runs once, on demand)
    ALERT_COOLDOWN      0 s     (deterministic notifications)
    SEED_HISTORY       off
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB = BACKEND_DIR / "data" / "apiguard_test.db"
TEST_OUTBOX = BACKEND_DIR / "data" / "test-outbox"
PORT = int(os.getenv("APIGUARD_TEST_PORT", "8123"))
BASE_URL = f"http://127.0.0.1:{PORT}"

os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{TEST_DB}",
        "ALERT_OUTBOX_DIR": str(TEST_OUTBOX),
        "SEED_HISTORY_ON_STARTUP": "false",
        "PROBE_INTERVAL_SECONDS": "3600",
        "ALERT_COOLDOWN_SECONDS": "0",
        "SELF_BASE_URL": BASE_URL,
        "ENVIRONMENT": "test",
    }
)

import httpx  # noqa: E402  (import after the environment is prepared)
import pytest  # noqa: E402

sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal  # noqa: E402


def _wait_ready(url: str, timeout_s: int = 90) -> None:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=3.0)
            if r.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001 - server not up yet
            last_error = exc
        time.sleep(0.4)
    raise RuntimeError(f"test server did not become ready at {url}: {last_error}")


@pytest.fixture(scope="session")
def server():
    """Start a private uvicorn instance for the whole test session."""
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(TEST_DB) + suffix)
        if path.exists():
            path.unlink()
    TEST_OUTBOX.mkdir(parents=True, exist_ok=True)

    log_path = BACKEND_DIR / "data" / "pytest-server.log"
    log = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1",
            "--port", str(PORT),
            "--log-level", "warning",
        ],
        cwd=str(BACKEND_DIR),
        env={**os.environ},
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_ready(f"{BASE_URL}/health")
        yield BASE_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:  # noqa: BLE001
            proc.kill()
        log.close()


@pytest.fixture(scope="session")
def base_url(server) -> str:
    return server


@pytest.fixture(scope="session")
def client(server):
    with httpx.Client(base_url=server, timeout=30.0) as c:
        yield c


@pytest.fixture()
def db():
    """Direct database session (read-only assertions against the test DB)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
