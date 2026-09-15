"""Phase snapshot and run contracts (owned by S0-DOM-001).

Snapshots are immutable after sealing; every same-phase primary intent
references one snapshot ID.
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from worldsim.domain.enums import PhaseRunState
from worldsim.domain.ids import CharacterId, PhaseRunId, SnapshotId, WorldId
from worldsim.domain.time import utcnow


class SnapshotCharacter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: CharacterId
    version: int = Field(ge=0)


class PhaseSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: SnapshotId
    world_id: WorldId
    phase_run_id: PhaseRunId
    absolute_index: int = Field(ge=0)
    schema_version: int = Field(default=1, ge=1)
    world_version: int = Field(ge=0)
    characters: list[SnapshotCharacter] = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_at: AwareDatetime = Field(default_factory=utcnow)


class PhaseRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: PhaseRunId
    world_id: WorldId
    absolute_index: int = Field(ge=0)
    state: PhaseRunState = PhaseRunState.CREATED
    created_at: AwareDatetime = Field(default_factory=utcnow)
    updated_at: AwareDatetime = Field(default_factory=utcnow)
