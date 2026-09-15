"""Ordered fictional phase transitions (owned by S0-SIM-001)."""

from __future__ import annotations

from worldsim.domain.enums import PhaseName
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.time import PHASE_ORDER, FictionalTime, absolute_index


def next_time(current: FictionalTime) -> FictionalTime:
    """Advance exactly one phase, rolling over to dawn of the next day."""
    position = PHASE_ORDER.index(current.phase) + 1
    if position >= len(PHASE_ORDER):
        return FictionalTime(day=current.day + 1, phase=PhaseName.DAWN)
    return FictionalTime(day=current.day, phase=PHASE_ORDER[position])


def require_next(current: FictionalTime, target_index: int) -> FictionalTime:
    """Accept only the immediately following phase; reject skips and repeats."""
    expected = current.absolute + 1
    if target_index != expected:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            f"phases must advance one step: current={current.absolute} target={target_index}",
            {"current": current.absolute, "target": target_index},
        )
    day, offset = divmod(expected, len(PHASE_ORDER))
    return FictionalTime(day=day + 1, phase=PHASE_ORDER[offset])


def require_aligned(day: int, phase: PhaseName, absolute: int) -> None:
    """Reject day/phase pairs that disagree with the absolute index."""
    if absolute_index(day, phase) != absolute:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            "day/phase disagrees with the absolute phase index",
            {"day": day, "phase": phase.value, "absolute": absolute},
        )
