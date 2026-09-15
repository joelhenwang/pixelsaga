"""Shared adapter failures (owned by S0-UOW-001)."""

from __future__ import annotations

from uuid import UUID

from worldsim.domain.errors import DomainError, ErrorCode


def missing(kind: str, identity: UUID) -> DomainError:
    return DomainError(ErrorCode.NOT_FOUND, f"unknown {kind}: {identity}")


def version_conflict(kind: str, identity: UUID, expected: int, actual: int) -> DomainError:
    return DomainError(
        ErrorCode.VERSION_CONFLICT,
        f"stale {kind} {identity}: expected={expected} actual={actual}",
        {"kind": kind, "id": str(identity), "expected": expected, "actual": actual},
    )
