"""Short-term resource bounds (owned by S0-SIM-001).

Stamina and mana live on 0-100 with no debt in Stage 0: spending past
zero fails, recovery caps at one hundred.
"""

from __future__ import annotations

from worldsim.domain.errors import DomainError, ErrorCode

RESOURCE_MIN = 0
RESOURCE_MAX = 100

REST_STAMINA_PER_PHASE = 10
REST_MANA_PER_PHASE = 5


def spend(current: int, cost: int) -> int:
    """Pay a cost or fail; never returns a negative balance."""
    if cost < 0:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "cost cannot be negative")
    remaining = current - cost
    if remaining < RESOURCE_MIN:
        raise DomainError(
            ErrorCode.INSUFFICIENT_RESOURCE,
            f"insufficient resource: have={current} cost={cost}",
            {"current": current, "cost": cost},
        )
    return remaining


def restore(current: int, amount: int) -> int:
    """Recover toward the cap; already-full stays full."""
    if amount < 0:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "recovery cannot be negative")
    return min(RESOURCE_MAX, current + amount)


def rest_recovery(duration_phases: int) -> tuple[int, int]:
    """Deterministic (stamina, mana) recovery for one rest."""
    if duration_phases < 1:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "rest needs at least one phase")
    return (
        duration_phases * REST_STAMINA_PER_PHASE,
        duration_phases * REST_MANA_PER_PHASE,
    )
