"""Observation and recent-memory contracts (owned by S0-DOM-001).

An observation holds only permitted event facts for one observer. A memory
retains them with owner, visibility, and source links. Claims and beliefs
arrive with Stage 2.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import Visibility
from worldsim.domain.ids import CharacterId, EventId, MemoryId, ObservationId, WorldId


class ObservationFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=512)


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ObservationId
    world_id: WorldId
    event_id: EventId
    observer_character_id: CharacterId
    facts: list[ObservationFact] = Field(min_length=1)
    created_phase_index: int = Field(ge=0)


class RecentMemory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: MemoryId
    world_id: WorldId
    owner_character_id: CharacterId
    event_id: EventId | None = None
    observation_id: ObservationId | None = None
    text: str = Field(min_length=1, max_length=2000)
    visibility: Visibility = Visibility.PRIVATE
    created_phase_index: int = Field(ge=0)
