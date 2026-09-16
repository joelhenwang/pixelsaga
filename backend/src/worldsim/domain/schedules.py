"""Due-date effects fired by the phase tick (owned by S2-TIME-001).

A schedule is a promise the tick keeps: when the clock reaches the
due phase, the tick records one world event and marks the schedule
applied. Retries find applied rows and skip them; cancellation is
an explicit terminal state, never deletion.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import ScheduleStatus
from worldsim.domain.ids import ScheduleId, WorldId


class ScheduledEffect(BaseModel):
    """One due-date payload awaiting its phase."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ScheduleId
    world_id: WorldId
    due_absolute: int = Field(ge=0)
    kind: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    status: ScheduleStatus = ScheduleStatus.PENDING
    version: int = Field(default=0, ge=0)
