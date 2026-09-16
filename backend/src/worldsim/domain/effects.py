"""Typed candidate effect commands (owned by S0-DOM-001).

Effects are discriminated and versioned. Each carries the affected
aggregates plus the expected prior versions the canonical transaction
rechecks before commit. There is no generic set-field effect.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from worldsim.domain.enums import EffectType, ResourceKind
from worldsim.domain.ids import LocationId, RouteId
from worldsim.domain.perception import ObservationFact


class EffectBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    affected_ids: list[UUID] = Field(min_length=1)
    expected_versions: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _versions_cover_affected(self) -> Self:
        missing = [
            str(target) for target in self.affected_ids if str(target) not in self.expected_versions
        ]
        if missing:
            raise ValueError(f"expected_versions must cover every affected id: {missing}")
        return self


class AdvanceClockEffect(EffectBase):
    effect_type: Literal[EffectType.ADVANCE_CLOCK] = EffectType.ADVANCE_CLOCK
    from_index: int = Field(ge=0)
    to_index: int = Field(ge=0)

    @model_validator(mode="after")
    def _forward_only(self) -> Self:
        if self.to_index <= self.from_index:
            raise ValueError("clock must advance forward")
        return self


class MoveEntityEffect(EffectBase):
    effect_type: Literal[EffectType.MOVE_ENTITY] = EffectType.MOVE_ENTITY
    from_location_id: LocationId
    to_location_id: LocationId
    route_id: RouteId | None = None

    @model_validator(mode="after")
    def _changes_location(self) -> Self:
        if self.to_location_id == self.from_location_id:
            raise ValueError("move must change location")
        return self


class ResourceAdjustedEffect(EffectBase):
    effect_type: Literal[EffectType.RESOURCE_ADJUSTED] = EffectType.RESOURCE_ADJUSTED
    resource: ResourceKind
    delta: int

    @model_validator(mode="after")
    def _nonzero_adjustment(self) -> Self:
        if self.delta == 0:
            raise ValueError("resource adjustment must be nonzero")
        return self


class ObservationRecordedEffect(EffectBase):
    effect_type: Literal[EffectType.RECORD_OBSERVATION] = EffectType.RECORD_OBSERVATION
    observer_character_id: UUID
    facts: list[ObservationFact] = Field(min_length=1)


class SkillProgressEffect(EffectBase):
    effect_type: Literal[EffectType.SKILL_PROGRESS] = EffectType.SKILL_PROGRESS
    character_id: UUID
    skill_key: str = Field(min_length=1, max_length=64)
    session_key: str = Field(min_length=1, max_length=128)


class MemoryRecordedEffect(EffectBase):
    effect_type: Literal[EffectType.RECORD_MEMORY] = EffectType.RECORD_MEMORY
    owner_character_id: UUID
    text: str = Field(min_length=1, max_length=2000)


DomainEffect = Annotated[
    AdvanceClockEffect
    | MoveEntityEffect
    | ResourceAdjustedEffect
    | ObservationRecordedEffect
    | MemoryRecordedEffect
    | SkillProgressEffect,
    Field(discriminator="effect_type"),
]
