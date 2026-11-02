"""
Sample REST API under monitoring.

Endpoints required by the assignment plus a few extras used by the failure lab:
    GET /health                 liveness + dependency status
    GET /users                  sample user collection
    GET /users/{user_id}        single user (404 scenario)
    GET /products               sample product catalogue
    GET /secure-data            API-key protected (401 scenario)
    GET /simulate-error         raises -> HTTP 500
    GET /simulate-timeout       sleeps N seconds (default 6s)
    GET /simulate-rate-limit    429 once the quota for the window is exhausted
    GET /simulate-auth-error    always 401
"""
from __future__ import annotations

import asyncio
import random
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.core.config import settings
from app.schemas import HealthResponse, Product, User

router = APIRouter(tags=["Sample API"])

START_TIME = time.time()
DB_STATUS = "connected"

# --------------------------------------------------------------------------- #
# Sample datasets (deterministic so the demo is reproducible)
# --------------------------------------------------------------------------- #
FIRST_NAMES = [
    "Aarav", "Vihaan", "Ananya", "Diya", "Rohan", "Ishaan", "Kavya", "Meera",
    "Aditya", "Sanya", "Kiran", "Nikhil", "Priya", "Rahul", "Sneha", "Varun",
]
LAST_NAMES = ["Reddy", "Sharma", "Naidu", "Iyer", "Rao", "Kumar", "Menon", "Patel", "Das", "Gupta"]
ROLES = ["admin", "editor", "viewer", "analyst", "support"]

USERS: list[dict[str, Any]] = [
    {
        "id": i + 1,
        "name": f"{FIRST_NAMES[i % len(FIRST_NAMES)]} {LAST_NAMES[(i * 3) % len(LAST_NAMES)]}",
        "email": f"user{i + 1}@apiguard.demo",
        "role": ROLES[i % len(ROLES)],
        "active": i % 7 != 0,
    }
    for i in range(24)
]

CATEGORIES = ["Electronics", "Home & Kitchen", "Books", "Sports", "Apparel", "Grocery"]
PRODUCT_NAMES = [
    "Aurora Wireless Earbuds", "Nimbus Smart Speaker", "Vertex Mechanical Keyboard",
    "Lumen Desk Lamp", "Terra Ceramic Cookware", "Pulse Fitness Band",
    "Cirrus Running Shoes", "Onyx Backpack", "Solis Water Bottle",
    "Kite Notebook Set", "Drift Coffee Beans", "Halo Monitor Stand",
]
PRODUCTS: list[dict[str, Any]] = [
    {
        "id": i + 1,
        "sku": f"AG-{1000 + i}",
        "name": f"{PRODUCT_NAMES[i % len(PRODUCT_NAMES)]} {chr(65 + (i // len(PRODUCT_NAMES)))}",
        "category": CATEGORIES[i % len(CATEGORIES)],
        "price": round(random.Random(i).uniform(199.0, 14999.0), 2),
        "stock": random.Random(i + 99).randint(0, 500),
    }
    for i in range(36)
]

# --------------------------------------------------------------------------- #
# In-memory rate limiter (per client IP)
# --------------------------------------------------------------------------- #
_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def _rate_limited(client_ip: str) -> tuple[bool, int]:
    now = time.time()
    bucket = _BUCKETS[client_ip]
    window = settings.RATE_LIMIT_WINDOW_SECONDS
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    allowed = len(bucket) < settings.RATE_LIMIT_MAX_REQUESTS
    if allowed:
        bucket.append(now)
    remaining = max(0, settings.RATE_LIMIT_MAX_REQUESTS - len(bucket))
    return (not allowed), remaining


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get("/health", response_model=HealthResponse, summary="API health status")
async def health(request: Request, degraded: bool = Query(False, description="Force an unhealthy response")) -> Any:
    """Returns the health of the service and its dependencies."""
    from sqlalchemy import func as _func  # local import to keep startup light
    from app.database import SessionLocal
    from app.models import Check

    checks_recorded = 0
    db_status = DB_STATUS
    try:
        db = SessionLocal()
        try:
            checks_recorded = db.query(_func.count(Check.id)).scalar() or 0
        finally:
            db.close()
    except Exception:  # pragma: no cover - report the dependency as unavailable
        db_status = "unavailable"

    if degraded:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "reason": "dependency 'cache' failed readiness probe",
                "service": settings.APP_NAME,
            },
        )

    return HealthResponse(
        status="healthy",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(timezone.utc),
        uptime_seconds=round(time.time() - START_TIME, 2),
        database=db_status,
        checks_recorded=checks_recorded,
    )


@router.get("/users", response_model=list[User], summary="Sample user data")
async def list_users(limit: int = Query(10, ge=1, le=100)) -> list[dict[str, Any]]:
    return USERS[:limit]


@router.get("/users/{user_id}", response_model=User, summary="Single user (404 when unknown)")
async def get_user(user_id: int) -> dict[str, Any]:
    for user in USERS:
        if user["id"] == user_id:
            return user
    raise HTTPException(status_code=404, detail=f"user {user_id} not found")


@router.get("/products", response_model=list[Product], summary="Sample product data")
async def list_products(
    limit: int = Query(12, ge=1, le=100),
    category: str | None = Query(None),
) -> list[dict[str, Any]]:
    items = PRODUCTS
    if category:
        items = [p for p in items if p["category"].lower() == category.lower()]
    return items[:limit]


@router.get("/secure-data", summary="API key protected resource")
async def secure_data(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    """Returns protected data when a valid X-API-Key header is supplied."""
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "missing_api_key",
                "message": "Provide a valid API key in the X-API-Key header.",
            },
        )
    if x_api_key not in settings.valid_api_keys:
        raise HTTPException(
            status_code=403,
            detail={"error": "invalid_api_key", "message": "The supplied API key is not valid or has expired."},
        )
    return {
        "status": "ok",
        "data": {"region": "ap-south-1", "plan": "enterprise", "seats": 250, "renewal": "2027-01-31"},
        "granted_to": x_api_key[:6] + "***",
    }


# --------------------------------------------------------------------------- #
# Failure simulation endpoints
# --------------------------------------------------------------------------- #
@router.get("/simulate-error", summary="Simulates a server error (HTTP 500)")
async def simulate_error(mode: str = Query("exception", pattern="^(exception|dependency)$")) -> dict[str, Any]:
    """Raises an unhandled exception so the monitor can detect a genuine 500."""
    if mode == "dependency":
        # Simulates a broken upstream contract (KeyError -> 500)
        payload: dict[str, Any] = {}
        return payload["inventory"]["items"]  # noqa: B018 - KeyError on purpose
    raise RuntimeError("Simulated upstream failure: inventory service returned no data")


@router.get("/simulate-timeout", summary="Simulates a slow / timing-out response")
async def simulate_timeout(seconds: float = Query(settings.SIMULATED_TIMEOUT_SECONDS, ge=0.1, le=30)) -> dict[str, Any]:
    """Sleeps for `seconds` - use a value above the probe timeout (10s) to force a real timeout."""
    await asyncio.sleep(seconds)
    return {"status": "ok", "slept_seconds": seconds, "note": "slow response returned"}


@router.get("/simulate-rate-limit", summary="Simulates rate limiting (HTTP 429)")
async def simulate_rate_limit(request: Request) -> Any:
    """Allows N requests per minute per client, then returns 429."""
    client_ip = request.client.host if request.client else "unknown"
    limited, remaining = _rate_limited(client_ip)
    if limited:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Quota of {settings.RATE_LIMIT_MAX_REQUESTS} requests / {settings.RATE_LIMIT_WINDOW_SECONDS}s exceeded.",
                "retry_after_seconds": settings.RATE_LIMIT_WINDOW_SECONDS,
            },
            headers={"Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS)},
        )
    return {
        "status": "ok",
        "remaining": remaining,
        "limit": settings.RATE_LIMIT_MAX_REQUESTS,
        "window_seconds": settings.RATE_LIMIT_WINDOW_SECONDS,
    }


@router.get("/simulate-auth-error", summary="Always returns HTTP 401")
async def simulate_auth_error() -> Any:
    raise HTTPException(
        status_code=401,
        detail={
            "error": "unauthorized",
            "message": "Invalid or expired credentials (simulated authentication failure).",
        },
    )
