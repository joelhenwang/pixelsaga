"""Command envelopes and Stage 0 action intents (owned by S0-DOM-001).

Every state-changing command carries identity, idempotency, actor, world,
expected versions, type/version, payload, and audit metadata. Stage 0
scripted actions run inside phase advancement; the envelope families for
player/director/deity input activate with their owning stages.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from worldsim.domain.enums import ActionFamily, CommandType, UserRole
from worldsim.domain.ids import CharacterId, CommandId, LocationId, RouteId, SnapshotId, WorldId
from worldsim.domain.time import utcnow


class AuditMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_by: str = Field(min_length=1, max_length=128)
    requested_at: AwareDatetime = Field(default_factory=utcnow)


class CommandBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_id: CommandId
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor_role: UserRole
    world_id: WorldId
    expected_versions: dict[str, int] = Field(default_factory=dict)
    audit: AuditMeta


class SeedWorldCommand(CommandBase):
    command_type: Literal[CommandType.SEED_WORLD] = CommandType.SEED_WORLD
    schema_version: Literal[1] = 1
    seed_version: str = Field(min_length=1, max_length=64)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class AdvancePhaseCommand(CommandBase):
    command_type: Literal[CommandType.ADVANCE_PHASE] = CommandType.ADVANCE_PHASE
    schema_version: Literal[1] = 1


class PauseSimulationCommand(CommandBase):
    command_type: Literal[CommandType.PAUSE_SIMULATION] = CommandType.PAUSE_SIMULATION
    schema_version: Literal[1] = 1


class ResumeSimulationCommand(CommandBase):
    command_type: Literal[CommandType.RESUME_SIMULATION] = CommandType.RESUME_SIMULATION
    schema_version: Literal[1] = 1


class ActionBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: CharacterId
    snapshot_id: SnapshotId


class WaitAction(ActionBase):
    family: Literal[ActionFamily.WAIT] = ActionFamily.WAIT


class RestAction(ActionBase):
    family: Literal[ActionFamily.REST] = ActionFamily.REST
    duration_phases: int = Field(default=1, ge=1)


class ObserveAction(ActionBase):
    family: Literal[ActionFamily.OBSERVE] = ActionFamily.OBSERVE
    focus: str = Field(default="surroundings", min_length=1, max_length=256)


class MoveAction(ActionBase):
    family: Literal[ActionFamily.MOVE] = ActionFamily.MOVE
    destination_location_id: LocationId
    route_id: RouteId | None = None


ActionIntent = Annotated[
    WaitAction | RestAction | ObserveAction | MoveAction,
    Field(discriminator="family"),
]
