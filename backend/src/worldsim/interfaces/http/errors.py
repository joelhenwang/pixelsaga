"""Stable errors and request identity (owned by S0-API-001).

Domain codes map to HTTP status without leaking internals: invariant
violations and unexpected failures return 500 with the code and a safe
message. Every response carries ``X-Request-ID``; every envelope echoes
it so logs and client reports join.
"""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from worldsim.application.correlation import request_id_var
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.interfaces.http.schemas import ErrorEnvelope

_STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.VERSION_CONFLICT: 409,
    ErrorCode.IDEMPOTENCY_CONFLICT: 409,
    ErrorCode.PRECONDITION_FAILED: 409,
    ErrorCode.VALIDATION_FAILED: 422,
    ErrorCode.UNSUPPORTED_ACTION: 422,
    ErrorCode.INSUFFICIENT_RESOURCE: 422,
    ErrorCode.INVARIANT_VIOLATED: 500,
}


def status_for(code: ErrorCode) -> int:
    return _STATUS_BY_CODE.get(code, 400)


def envelope(
    code: str, message: str, request_id: str, details: dict[str, object]
) -> dict[str, object]:
    return ErrorEnvelope.model_validate(
        {
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
                "details": details,
            }
        }
    ).model_dump(mode="json")


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    request_id = getattr(request.state, "request_id", "") or request_id_var.get()
    return JSONResponse(
        status_code=status_for(exc.code),
        content=envelope(exc.code.value.upper(), str(exc), request_id, dict(exc.details)),
    )


async def unhandled_error_handler(request: Request, _exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "") or request_id_var.get()
    return JSONResponse(
        status_code=500,
        content=envelope("INTERNAL_ERROR", "unexpected failure", request_id, {}),
    )


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign (or echo) a request ID, expose it to handlers and logs."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        access = logging.getLogger("worldsim.access")
        request_id = request.headers.get("X-Request-ID") or f"req-{uuid4().hex[:12]}"
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            status = response.status_code
        except Exception:
            raise
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            access.info(
                "%s %s -> %s (%sms)",
                request.method,
                request.url.path,
                status,
                latency_ms,
                extra={"method": request.method, "path": request.url.path, "status": status},
            )
            request_id_var.reset(token)
        return response
