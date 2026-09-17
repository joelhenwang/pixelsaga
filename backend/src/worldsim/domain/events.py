"""World event and committed-effect contracts (owned by S0-DOM-001).

Events are immutable canon headers; narration stays linked presentation
data and is never required to reconstruct state.
"""

from __future__ import annotations

from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from worldsim.domain.effects import DomainEffect
from worldsim.domain.enums import EventType, Visibility
from worldsim.domain.ids import CommandId, EventId, PhaseRunId, TaskId, WorldId
from worldsim.domain.time import utcnow


class WorldEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: EventId
    world_id: WorldId
    sequence: int = Field(ge=1)
    event_type: EventType
    schema_version: int = Field(default=1, ge=1)
    absolute_index: int = Field(ge=0)
    phase_run_id: PhaseRunId | None = None
    source_command_id: CommandId | None = None
    source_task_id: TaskId | None = None
    participant_ids: list[UUID] = Field(default_factory=list)
    summary: dict[str, str] = Field(default_factory=dict)
    visibility: Visibility = Visibility.PUBLIC
    random_seed: int | None = None
    random_algorithm: str | None = Field(default=None, max_length=64)
    random_result: str | None = Field(default=None, max_length=512)
    created_at: AwareDatetime = Field(default_factory=utcnow)


class CommittedEffect(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: EventId
    ordinal: int = Field(ge=0)
    effect: DomainEffect


class WorldEventRecord(BaseModel):
    """One event with its ordered effects; ordinals must be contiguous."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: WorldEvent
    effects: list[CommittedEffect] = Field(min_length=1)

    @model_validator(mode="after")
    def _ordinals_contiguous(self) -> Self:
        ordinals = sorted(item.ordinal for item in self.effects)
        if ordinals != list(range(len(self.effects))):
            raise ValueError("effect ordinals must be contiguous from zero")
        if any(item.event_id != self.event.id for item in self.effects):
            raise ValueError("every effect must reference the record event")
        return self
