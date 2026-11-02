"""
Request context middleware.

Every request gets:
  * a correlation id (X-Request-ID) echoed back to the caller
  * an X-Response-Time header
  * a row in `request_logs` (real traffic volume / status / latency)
  * Prometheus counters + latency histogram

Unhandled exceptions are captured into `error_logs` with the full traceback -
that record is the primary evidence used by the RCA engine.
"""
from __future__ import annotations

import time
import traceback
import uuid
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.database import SessionLocal
from app.models import ErrorLog, RequestLog
from app.monitoring import metrics
from app.monitoring.rca import sanitize

SKIP_LOG_PREFIXES = (
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/monitor",  # control-plane traffic is not part of the monitored sample API
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        start = time.perf_counter()
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:  # noqa: BLE001 - capture, then answer cleanly
            # We convert the exception into a structured 500 *here* instead of
            # letting it bubble up to Starlette's ServerErrorMiddleware: that
            # middleware re-raises after sending the response, which makes
            # uvicorn reset the keep-alive connection.
            duration_ms = (time.perf_counter() - start) * 1000
            self._log_error(request, request_id, exc, duration_ms)
            metrics.observe_request(request.method, request.url.path, 500, duration_ms / 1000.0)
            payload = {
                "error": "internal_server_error",
                "message": str(exc),
                "exception_type": type(exc).__name__,
                "path": request.url.path,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
            response = JSONResponse(status_code=500, content=payload)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
            return response
        duration_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

        if not request.url.path.startswith(SKIP_LOG_PREFIXES):
            self._log_request(request, request_id, status_code, duration_ms)
            metrics.observe_request(request.method, request.url.path, status_code, duration_ms / 1000.0)
        return response

    # ------------------------------------------------------------------ logs
    @staticmethod
    def _log_request(request: Request, request_id: str, status_code: int, duration_ms: float) -> None:
        try:
            db = SessionLocal()
            try:
                db.add(
                    RequestLog(
                        ts=datetime.utcnow(),
                        method=request.method,
                        path=request.url.path,
                        status_code=status_code,
                        latency_ms=round(duration_ms, 2),
                        request_id=request_id,
                        client_ip=request.client.host if request.client else "",
                        user_agent=(request.headers.get("user-agent", "") or "")[:250],
                        is_error=status_code >= 400,
                    )
                )
                db.commit()
            finally:
                db.close()
        except Exception:  # pragma: no cover - logging must never break a request
            pass

    @staticmethod
    def _log_error(request: Request, request_id: str, exc: Exception, duration_ms: float) -> None:
        tb = sanitize(traceback.format_exc())
        try:
            db = SessionLocal()
            try:
                db.add(
                    ErrorLog(
                        ts=datetime.utcnow(),
                        request_id=request_id,
                        method=request.method,
                        path=request.url.path,
                        exception_type=type(exc).__name__,
                        exception_message=str(exc)[:1000],
                        traceback=tb,
                        status_code=500,
                        client_ip=request.client.host if request.client else "",
                        latency_ms=round(duration_ms, 2),
                    )
                )
                db.commit()
            finally:
                db.close()
        except Exception:  # pragma: no cover
            pass
