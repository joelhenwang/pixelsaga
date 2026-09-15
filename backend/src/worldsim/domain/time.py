"""Ten-phase fictional calendar and absolute phase index (owned by S0-DOM-001)."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import PhaseName

PHASE_ORDER: tuple[PhaseName, ...] = (
    PhaseName.DAWN,
    PhaseName.SUNRISE,
    PhaseName.MORNING,
    PhaseName.NOON,
    PhaseName.AFTERNOON,
    PhaseName.SUNSET,
    PhaseName.DUSK,
    PhaseName.EVENING,
    PhaseName.NIGHT,
    PhaseName.MIDNIGHT,
)

PHASES_PER_DAY = len(PHASE_ORDER)


def utcnow() -> datetime:
    return datetime.now(UTC)


def absolute_index(day: int, phase: PhaseName) -> int:
    """Map a 1-based day plus phase to a 0-based absolute phase index."""
    if day < 1:
        raise ValueError("day starts at 1")
    return (day - 1) * PHASES_PER_DAY + PHASE_ORDER.index(phase)


def split_absolute(index: int) -> tuple[int, PhaseName]:
    """Split an absolute phase index back into 1-based day and phase."""
    if index < 0:
        raise ValueError("absolute phase index cannot be negative")
    day, offset = divmod(index, PHASES_PER_DAY)
    return day + 1, PHASE_ORDER[offset]


class FictionalTime(BaseModel):
    """Immutable fictional position; operational UTC time stays separate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    day: int = Field(ge=1)
    phase: PhaseName

    @property
    def absolute(self) -> int:
        return absolute_index(self.day, self.phase)
