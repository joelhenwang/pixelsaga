"""Travel and persistent activity contracts (owned by S2-CONTRACT-001).

Activities span phases: the tick advances progress, interruption
freezes it, completion applies effects. Travel routes are world
facts with phase durations and stamina costs; the activity packet
owns their persistence while location rows keep nested display
routes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import ActivityKind, ActivityStatus, FocusSlot
from worldsim.domain.ids import ActivityId, CharacterId, LocationId, RouteId, WorldId


class Activity(BaseModel):
    """One persistent undertaking. Progress counts committed phases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ActivityId
    world_id: WorldId
    character_id: CharacterId
    kind: ActivityKind
    status: ActivityStatus = ActivityStatus.PLANNED
    start_absolute: int = Field(ge=0)
    duration_phases: int = Field(ge=1)
    progress_phases: int = Field(default=0, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=0, ge=0)


class TravelRoute(BaseModel):
    """A traversable world fact: origin, destination, cost."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: RouteId
    world_id: WorldId
    from_location_id: LocationId
    to_location_id: LocationId
    duration_phases: int = Field(ge=1)
    stamina_cost: int = Field(ge=0)
    version: int = Field(default=0, ge=0)


def focus_for_seat(seated: int) -> FocusSlot:
    """Seat order decides the focus slot: two mains, two subs, rest companions."""
    if seated < 2:
        return FocusSlot.MAIN
    if seated < 4:
        return FocusSlot.SUB
    return FocusSlot.COMPANION


def effective_progress(activity: Activity, absolute: int) -> int:
    """Phases done: baked progress plus elapsed time while active, capped."""
    if activity.status != ActivityStatus.ACTIVE:
        return activity.progress_phases
    elapsed = max(0, absolute - activity.start_absolute)
    return min(activity.duration_phases, activity.progress_phases + elapsed)
