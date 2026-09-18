"""Bounded persistent world conditions (owned by REVAMP-P09).

A condition is stateful canon, not narration: deterministic phase
ticks apply bounded effects and emit inspectable events until the
condition expires or recovers. The initial supported type is illness;
unknown causes may be known to God but concealed from characters.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.ids import (
    InterventionId,
    LocationId,
    WorldConditionId,
    WorldId,
    new_world_condition_id,
)


class ConditionType(StrEnum):
    ILLNESS = "illness"


class ConditionStatus(StrEnum):
    ACTIVE = "active"
    RECOVERED = "recovered"
    EXPIRED = "expired"


class WorldCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: WorldConditionId
    world_id: WorldId
    kind: ConditionType
    public_label: str = Field(min_length=1, max_length=128)
    detail: str = Field(default="", max_length=1024)
    scope_location_ids: list[LocationId] = Field(min_length=1)
    severity: int = Field(ge=1, le=5)
    started_absolute: int = Field(ge=0)
    ends_absolute: int = Field(ge=0)
    status: ConditionStatus = ConditionStatus.ACTIVE
    source_intervention_id: InterventionId | None = None
    version: int = Field(default=0, ge=0)


__all__ = [
    "ConditionStatus",
    "ConditionType",
    "WorldCondition",
    "new_world_condition_id",
]
