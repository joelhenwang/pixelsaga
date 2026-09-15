"""Stable domain error taxonomy (owned by S0-DOM-001).

Codes are part of the contract surface: never rename a code, only add new
ones alongside a schema version.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    VALIDATION_FAILED = "validation_failed"
    NOT_FOUND = "not_found"
    VERSION_CONFLICT = "version_conflict"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    FORBIDDEN = "forbidden"
    PRECONDITION_FAILED = "precondition_failed"
    UNSUPPORTED_ACTION = "unsupported_action"
    INVARIANT_VIOLATED = "invariant_violated"
    INSUFFICIENT_RESOURCE = "insufficient_resource"


class DomainError(Exception):
    """Domain failure with a stable machine-readable code."""

    def __init__(
        self, code: ErrorCode, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details) if details else {}
