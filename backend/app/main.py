"""
APIGuard - FastAPI sample API + monitoring service.

Layout
------
    GET  /                         service index
    GET  /health  /users ...       the sample API under monitoring
    GET  /monitor/*                monitoring control plane (dashboard API)
    GET  /metrics                  Prometheus exposition format
    GET  /docs                     Swagger UI
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.config import settings
from app.core.middleware import RequestContextMiddleware
from app.database import Base, engine as db_engine
from app.monitoring import metrics, seed
from app.monitoring.engine import engine as monitor_engine
from app.routers import monitor as monitor_router
from app.routers import sample as sample_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- startup -----------------------------------------------------------
    Base.metadata.create_all(bind=db_engine)
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        seed.seed_endpoints(db)
        if settings.SEED_HISTORY_ON_STARTUP:
            result = seed.seed_history(db, hours=settings.SEED_HISTORY_HOURS)
            print(f"[apiguard] history seed: {result}")
    finally:
        db.close()

    await monitor_engine.start()
    print(
        f"[apiguard] {settings.APP_NAME} v{settings.APP_VERSION} ready on "
        f"{settings.HOST}:{settings.PORT} (probe every {settings.PROBE_INTERVAL_SECONDS}s)"
    )
    yield
    # ---- shutdown ----------------------------------------------------------
    await monitor_engine.stop()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Sample REST API (FastAPI) with a full monitoring stack: synthetic probing, "
        "Prometheus metrics, incident detection, root cause analysis and multi-channel alerting."
    ),
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Global error handling - every unhandled exception becomes an HTTP 500 whose
# traceback is persisted in `error_logs` (the RCA engine reads it back).
# --------------------------------------------------------------------------- #
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request.headers.get("x-request-id", "")
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": str(exc),
            "exception_type": type(exc).__name__,
            "path": request.url.path,
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    )


# --------------------------------------------------------------------------- #
# Routers
# --------------------------------------------------------------------------- #
app.include_router(sample_router.router)
app.include_router(monitor_router.router)


@app.get("/", tags=["Meta"], summary="Service index")
async def index() -> dict:
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
        "prometheus_metrics": "/metrics",
        "monitoring_api": "/monitor/summary",
        "sample_endpoints": [
            "/health",
            "/users",
            "/products",
            "/secure-data",
            "/simulate-error",
            "/simulate-timeout",
            "/simulate-rate-limit",
            "/simulate-auth-error",
        ],
        "engine": monitor_engine.status(),
    }


@app.get("/metrics", include_in_schema=False, tags=["Meta"])
async def prometheus_metrics():
    from fastapi.responses import Response

    return Response(content=generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)
