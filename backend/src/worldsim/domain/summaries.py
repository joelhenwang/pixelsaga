"""Daily summary contracts (owned by S2-SUMMARY-001).

A summary is one owner's non-authoritative retelling of one day,
built only from that owner's observations and memories. Versions
accumulate: regeneration writes a new row, never rewrites. Raw
records are never modified, and fallback records say exactly what
they are.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.ids import CharacterId, SummaryId, WorldId


class DailySummary(BaseModel):
    """One version of one owner's account of one day."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: SummaryId
    world_id: WorldId
    owner_id: CharacterId
    day: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=4000)
    source_ids: list[str] = Field(default_factory=list)
    profile_version: str = Field(default="", max_length=64)
    prompt_version: str = Field(default="", max_length=64)
    fallback: bool = False
    version: int = Field(default=1, ge=1)


def day_range(day: int, phases_per_day: int = 10) -> tuple[int, int]:
    """Absolute phase bounds for a 1-based day, inclusive."""
    start = (day - 1) * phases_per_day
    return start, start + phases_per_day - 1


def fallback_text(observations: int, memories: int) -> str:
    """Structural fallback: counts only, no invention."""
    return (
        f"A quiet account: {observations} observations and {memories} memories recorded this day."
    )
