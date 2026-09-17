"""API key enforcement (owned by S5-HARD-001).

Startup refuses a public bind without a key; this middleware is the
other half: when a key is configured, every request outside the
health probes must bear it. No key configured means local loopback
development, and everything stays open.
"""

from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from worldsim.interfaces.http.errors import envelope

EXEMPT_PATHS = frozenset({"/api/v1/health/live", "/api/v1/health/ready"})


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, expected_key: str | None) -> None:
        super().__init__(app)
        self._expected = expected_key

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if self._expected and request.url.path not in EXEMPT_PATHS:
            presented = request.headers.get("authorization", "")
            scheme, _, token = presented.partition(" ")
            if scheme.lower() != "bearer" or not secrets.compare_digest(token, self._expected):
                request_id = getattr(request.state, "request_id", "")
                return JSONResponse(
                    status_code=401,
                    content=envelope("UNAUTHORIZED", "valid bearer key required", request_id, {}),
                )
        return await call_next(request)
