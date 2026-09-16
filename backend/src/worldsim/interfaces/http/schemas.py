"""Stage 0 request/response DTOs (owned by S0-API-001).

Never ORM structures: every model here is an explicit projection of a
domain record. UUIDs render as strings; operational timestamps are
ISO-8601 UTC.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import PhaseName


class HealthLiveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"] = "ok"


class DependencyCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    status: Literal["ok", "degraded", "failed"]
    detail: str = ""


class ReadyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready", "degraded"]
    version: str
    environment: str
    migration_head: str | None
    schema_version: int
    checks: list[DependencyCheck]


class WorldResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: str
    status: str
    day: int
    phase: PhaseName
    absolute_index: int
    seed_version: str
    version: int


class ClockResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    day: int
    phase: PhaseName
    absolute_index: int


class CurrentPhaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    absolute_index: int
    day: int
    phase: PhaseName
    run_id: UUID | None
    run_state: str | None


class EventEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int
    id: UUID
    event_type: str
    absolute_index: int
    phase_run_id: UUID
    effect_count: int


class EventsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entries: list[EventEntry]
    next_after: int


class SeedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    seed_version: str
    content_hash: str
    duplicate: bool


class AdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID


class AdvanceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    sequence: int


class AdvanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_id: UUID
    run_id: UUID
    task_id: UUID
    status: Literal["completed"] = "completed"
    world_version: int
    event_cursor: int
    idempotent_replay: bool
    result: AdvanceResult


class ReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID


class ReconcileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tasks_requeued: int
    outbox_requeued: int
    open_run_id: UUID | None
    open_state: str | None


class TaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    kind: str
    state: str
    owner: str | None
    attempt: int | None
    max_attempts: int | None
    expires_at: datetime | None


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    request_id: str
    details: dict[str, object] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    error: ErrorDetail


class CharacterSummary(BaseModel):
    """Stage 1 character listing (owned by S1-API-001)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: str
    life_status: str
    location_id: UUID


class CharacterDetail(BaseModel):
    """Stage 1 character view; card excerpt only for self or watcher."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: str
    life_status: str
    location_id: UUID
    card: dict[str, object] | None = None
    state: dict[str, object] | None = None


class ParticipantView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: UUID
    role: str


class IntentView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    author_character_id: UUID
    family: str
    detail: dict[str, object] | None = None


class AttemptView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    actor_character_id: UUID
    observable_summary: str
    status: str


class ReactionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    reactor_character_id: UUID
    family: str
    detail: dict[str, object] | None = None


class ResolutionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: str
    resolver: str
    rationale: str


class SceneDetail(BaseModel):
    """Stage 1 scene view scoped to the caller perspective (S1-API-001)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    phase_run_id: UUID
    status: str
    beat_budget: int
    event_id: UUID | None = None
    participants: list[ParticipantView] = Field(default_factory=list)
    intents: list[IntentView] = Field(default_factory=list)
    attempts: list[AttemptView] = Field(default_factory=list)
    reactions: list[ReactionView] = Field(default_factory=list)
    resolution: ResolutionView | None = None


class SceneSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    status: str
    event_id: UUID | None = None
    participant_ids: list[UUID] = Field(default_factory=list)


class BeatView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    speaker_id: UUID | None = None
    kind: str
    text: str
    source_event_id: UUID


class ModelRunView(BaseModel):
    """Watcher-only model audit view: metadata, never raw hidden content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: UUID
    role: str
    profile: str
    status: str
    actor_id: UUID | None = None
    manifest_id: UUID | None = None
    rendered_hash: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


class Stage1AdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    absolute_index: int = Field(ge=1)
    player_intents: dict[str, dict[str, object]] = Field(default_factory=dict)


class Stage1SceneOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_id: UUID
    event_id: UUID
    resolution_outcome: str
    narration: str


class Stage1AdvanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    world_id: UUID
    absolute_index: int
    snapshot_id: UUID
    scenes: list[Stage1SceneOutcome] = Field(default_factory=list)
    duplicate: bool = False
    quiet: bool = False


class RunIdRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID


class PartyBeginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    name: str = Field(min_length=1, max_length=128)
    race: str = Field(default="human", max_length=64)
    character_class: str = Field(default="fighter", max_length=64)
    level: int = Field(default=1, ge=1, le=20)
    stats: dict[str, int] | None = None


class PartyMemberView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    name: str
    level: int
    character_class: str
    hp_current: int | None = None
    hp_max: int | None = None
    conditions: list[str] = Field(default_factory=list)
    version: int


class ActivityStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    character_id: UUID
    kind: str = Field(max_length=32)
    duration_phases: int | None = Field(default=None, ge=1, le=100)
    to_location_id: UUID | None = None
    skill: str | None = Field(default=None, max_length=64)


class ItemGiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    item_key: str = Field(max_length=64)
    owner_id: UUID | None = None
    quantity: int = Field(default=1, ge=1)


class ItemTransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    to_owner_id: UUID | None = None


class ItemView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    item_key: str
    owner_id: UUID | None
    quantity: int
    version: int


class ItemListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    owner_id: UUID | None
    members: list[ItemView] = Field(default_factory=list)


class SkillView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    skill_key: str
    progress: int
    sessions: int
    version: int


class SkillListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    character_id: UUID
    members: list[SkillView] = Field(default_factory=list)


class ActivityView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    character_id: UUID
    kind: str
    status: str
    start_absolute: int
    duration_phases: int
    progress_phases: int
    version: int


class ActivityListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    members: list[ActivityView] = Field(default_factory=list)


class RelationshipEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    source_id: UUID
    target_id: UUID
    dimension: str = Field(max_length=16)
    delta: int = Field(ge=-10, le=10)
    note: str = Field(default="", max_length=512)


class RelationshipView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    source_id: UUID
    target_id: UUID
    direction: str
    trust: int
    affection: int
    respect: int
    summary: str
    version: int


class RelationshipListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    character_id: UUID
    members: list[RelationshipView] = Field(default_factory=list)


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    speaker_id: UUID
    proposition: str = Field(min_length=1, max_length=1024)
    audience_location_id: UUID | None = None
    refutes_claim_id: UUID | None = None


class ClaimView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    speaker_id: UUID
    audience_location_id: UUID | None
    proposition: str
    refutes_claim_id: UUID | None
    version: int


class ClaimListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    viewer_id: UUID
    members: list[ClaimView] = Field(default_factory=list)


class BeliefView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    holder_id: UUID
    proposition: str
    confidence: float
    last_touched_absolute: int
    version: int


class BeliefListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    holder_id: UUID
    members: list[BeliefView] = Field(default_factory=list)


class RoleSelectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    role: str = Field(max_length=16)
    character_id: UUID | None = None


class RoleGrantView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    role: str
    character_id: UUID | None
    granted_absolute: int
    version: int


class DirectorProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    kind: str = Field(pattern="^(hook|arc)$")
    title: str = Field(min_length=1, max_length=128)
    purpose: str = Field(default="", max_length=1024)
    requested_powers: list[str] = Field(default_factory=list)
    participant_ids: list[UUID] = Field(default_factory=list)


class DirectorProposalView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    kind: str
    title: str
    reason: str


class DeityOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    character_id: UUID
    stamina: int | None = Field(default=None, ge=0, le=100)
    mana: int | None = Field(default=None, ge=0, le=100)
    life_status: str | None = Field(default=None, max_length=16)
    conditions: list[str] | None = None
    retcon: bool = False


class DeityOverrideView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    world_id: UUID
    character_id: UUID
    retcon: bool


class PartyRosterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    members: list[PartyMemberView] = Field(default_factory=list)
