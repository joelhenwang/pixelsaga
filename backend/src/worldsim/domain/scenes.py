"""Stage 1 intent, scene, reaction, and resolution contracts (owned by S1-CONTRACT-001).

Proposals flow one way: model (or player) proposes an Intent, validators
accept an Attempt, the assembler groups a Scene, the resolver produces
one Resolution, the canonical transaction commits exactly one event.
Nothing here mutates canon; statuses track the operational pipeline.
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from worldsim.domain.commands import ActionIntent
from worldsim.domain.effects import DomainEffect
from worldsim.domain.enums import (
    AttemptStatus,
    IntentStatus,
    ParticipantRole,
    ReactionStatus,
    ResolutionOutcome,
    ResolverKind,
    SceneStatus,
)
from worldsim.domain.ids import (
    AttemptId,
    CharacterId,
    EventId,
    IntentId,
    PhaseRunId,
    ReactionId,
    ResolutionId,
    SceneId,
    SnapshotId,
    WorldId,
)
from worldsim.domain.time import utcnow

#: Scene transitions the assembler and resolver may take. Terminal states
#: never leave; INVALID is terminal for a proposal (a new Intent restarts).
_SCENE_EDGES: dict[SceneStatus, frozenset[SceneStatus]] = {
    SceneStatus.PROPOSED: frozenset({SceneStatus.VALIDATING, SceneStatus.INVALID}),
    SceneStatus.VALIDATING: frozenset(
        {SceneStatus.READY, SceneStatus.INVALID, SceneStatus.RETRYABLE_FAILED}
    ),
    SceneStatus.READY: frozenset(
        {SceneStatus.RESOLVING, SceneStatus.RETRYABLE_FAILED, SceneStatus.TERMINAL_FAILED}
    ),
    SceneStatus.RESOLVING: frozenset(
        {SceneStatus.RESOLVED, SceneStatus.RETRYABLE_FAILED, SceneStatus.TERMINAL_FAILED}
    ),
    SceneStatus.RESOLVED: frozenset(
        {SceneStatus.COMMITTED, SceneStatus.RETRYABLE_FAILED, SceneStatus.TERMINAL_FAILED}
    ),
    SceneStatus.COMMITTED: frozenset(),
    SceneStatus.INVALID: frozenset(),
    SceneStatus.RETRYABLE_FAILED: frozenset(
        {SceneStatus.VALIDATING, SceneStatus.READY, SceneStatus.RESOLVING}
    ),
    SceneStatus.TERMINAL_FAILED: frozenset(),
}


def scene_transition_allowed(current: SceneStatus, target: SceneStatus) -> bool:
    return target in _SCENE_EDGES[current]


class ValidationIssue(BaseModel):
    """One structural or semantic rejection with a stable location path."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    location: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=512)


class DesiredEffect(BaseModel):
    """What the actor hopes to achieve. Non-authoritative by definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    effect_family: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=512)
    depends_on_intent_id: IntentId | None = None


class Intent(BaseModel):
    """One actor's proposed meaningful action from a sealed snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: IntentId
    world_id: WorldId
    snapshot_id: SnapshotId
    phase_run_id: PhaseRunId | None = None
    author_character_id: CharacterId
    action: ActionIntent
    desired_effects: list[DesiredEffect] = Field(default_factory=list)
    status: IntentStatus = IntentStatus.PROPOSED
    idempotency_key: str = Field(min_length=1, max_length=128)
    created_at: AwareDatetime = Field(default_factory=utcnow)


class Attempt(BaseModel):
    """Validated observable execution of an intent, before any outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: AttemptId
    world_id: WorldId
    intent_id: IntentId
    scene_id: SceneId | None = None
    actor_character_id: CharacterId
    observable_summary: str = Field(min_length=1, max_length=512)
    status: AttemptStatus = AttemptStatus.PENDING
    created_at: AwareDatetime = Field(default_factory=utcnow)


class Reaction(BaseModel):
    """Bounded response by one eligible participant to one attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ReactionId
    world_id: WorldId
    attempt_id: AttemptId
    scene_id: SceneId | None = None
    reactor_character_id: CharacterId
    action: ActionIntent
    status: ReactionStatus = ReactionStatus.PENDING
    created_at: AwareDatetime = Field(default_factory=utcnow)


class SceneParticipant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: CharacterId
    role: ParticipantRole


class Scene(BaseModel):
    """Causally interacting intents with one atomic outcome boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: SceneId
    world_id: WorldId
    phase_run_id: PhaseRunId
    snapshot_id: SnapshotId
    status: SceneStatus = SceneStatus.PROPOSED
    participants: list[SceneParticipant] = Field(min_length=1)
    intent_ids: list[IntentId] = Field(min_length=1)
    mutable_aggregate_ids: list[str] = Field(default_factory=list)
    beat_budget: int = Field(default=8, ge=1, le=64)
    resolution_id: ResolutionId | None = None
    event_id: EventId | None = None
    created_at: AwareDatetime = Field(default_factory=utcnow)
    updated_at: AwareDatetime = Field(default_factory=utcnow)


class Resolution(BaseModel):
    """One accepted outcome for a scene: typed effects plus evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ResolutionId
    world_id: WorldId
    scene_id: SceneId
    outcome: ResolutionOutcome
    resolver: ResolverKind
    profile_version: str = Field(default="", max_length=64)
    effects: list[DomainEffect] = Field(default_factory=list)
    rationale: str = Field(default="", max_length=2000)
    random_seed: int = Field(default=0, ge=0)
    created_at: AwareDatetime = Field(default_factory=utcnow)
