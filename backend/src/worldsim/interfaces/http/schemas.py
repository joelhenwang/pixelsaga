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
    character_id: UUID | None = None


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
    character_id: UUID | None = None
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
    from_location_id: UUID | None = None
    to_location_id: UUID | None = None
    route_id: UUID | None = None
    effective_progress_phases: int | None = None
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


class TimelineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int
    event_id: UUID
    event_type: str
    absolute_index: int
    snippet: str | None = None


class TimelineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    entries: list[TimelineEntry] = Field(default_factory=list)
    total: int
    next_after: int
    has_more: bool


class MapRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    to_location_id: UUID
    duration_phases: int


class MapPlace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: str
    region: str
    discovered: bool
    routes: list[MapRoute] = Field(default_factory=list)
    occupants: list[str] = Field(default_factory=list)
    occupant_ids: list[UUID] = Field(default_factory=list)


class MapResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    places: list[MapPlace] = Field(default_factory=list)


class DiaryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    phase: int
    text: str


class DiaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: UUID
    observations: list[DiaryEntry] = Field(default_factory=list)
    memories: list[DiaryEntry] = Field(default_factory=list)
    summaries: list[DiaryEntry] = Field(default_factory=list)
    digests: list[DiaryEntry] = Field(default_factory=list)


class HookView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    title: str
    status: str


class ArcView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    title: str
    status: str


class HookListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    hooks: list[HookView] = Field(default_factory=list)
    arcs: list[ArcView] = Field(default_factory=list)


class OperationsStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    open_run_id: UUID | None
    open_run_state: str | None
    pending_outbox: int
    total_events: int


class PartyRosterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    members: list[PartyMemberView] = Field(default_factory=list)


class MacroEffectView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    detail: str
    event_id: UUID | None = None
    target_ids: list[UUID] = Field(default_factory=list)


class MacroInterruptionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    at_absolute: int
    reason: str
    detail: str


class MacroRunView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    start_absolute: int
    end_absolute: int
    resolution: str
    state: str
    effects: list[MacroEffectView] = Field(default_factory=list)
    interruptions: list[MacroInterruptionView] = Field(default_factory=list)


class MacroRunsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    runs: list[MacroRunView] = Field(default_factory=list)


class LineageLinkView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    parent_id: UUID
    parent_name: str
    child_id: UUID
    child_name: str
    birth_absolute: int


class LineageRecordView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: UUID
    name: str
    birth_absolute: int
    death_absolute: int | None = None
    life_status: str
    succession_eligible: bool


class LineageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    links: list[LineageLinkView] = Field(default_factory=list)
    records: list[LineageRecordView] = Field(default_factory=list)


class FocusAssignmentView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slot: str
    version: int
    from_character_id: UUID | None = None
    from_name: str | None = None
    to_character_id: UUID
    to_name: str
    effective_absolute: int
    reason: str


class FocusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    assignments: list[FocusAssignmentView] = Field(default_factory=list)


class EraView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    era_id: UUID
    owner_id: UUID
    start_absolute: int
    end_absolute: int
    text: str
    source_ids: list[str] = Field(default_factory=list)
    version: int


class ErasResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    eras: list[EraView] = Field(default_factory=list)


class EndingView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    satisfied: bool
    evaluated_absolute: int
    window_start_absolute: int
    evidence_event_ids: list[str] = Field(default_factory=list)
    detail: str


class EndingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    endings: list[EndingView] = Field(default_factory=list)


class MacroAdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    day: int = Field(ge=1)
    resolution: str = Field(min_length=1, max_length=16)


class MacroAdvanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    state: str
    start_absolute: int
    end_absolute: int
    event_ids: list[UUID] = Field(default_factory=list)
    duplicate: bool


class EraComposeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    owner_id: UUID
    start_absolute: int = Field(ge=0)
    end_absolute: int = Field(ge=1)


class EndingsEvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    at_absolute: int = Field(ge=0)


class FocusAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    slot: str = Field(min_length=1, max_length=16)
    to_character_id: UUID
    reason: str = Field(min_length=1, max_length=500)
    effective_absolute: int = Field(ge=0)
    from_character_id: UUID | None = None


class ScheduleCancelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schedule_id: UUID
    status: str


class CharacterCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    name: str = Field(min_length=1, max_length=128)
    location_id: UUID
    appearance: str = Field(default="", max_length=2000)
    personality: str = Field(default="", max_length=2000)
    background: str = Field(default="", max_length=2000)


class PartyLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    character_id: UUID
    expected_version: int = Field(ge=0)


class ChronicleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int
    event_id: UUID
    event_type: str
    title: str
    text: str | None = None
    participant_ids: list[UUID] = Field(default_factory=list)
    location_id: UUID | None = None
    scene_id: UUID | None = None
    absolute_index: int
    revision: int = 0


class ChronicleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    entries: list[ChronicleEntry] = Field(default_factory=list)
    next_after: int
    has_more: bool
    watermark: int


class PresentationCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str
    character_id: UUID | None = None
    capabilities: list[str] = Field(default_factory=list)


class MapAnchorView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    location_id: UUID
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class MapManifestView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    version: int
    schematic: bool
    asset_id: UUID | None = None
    anchors: list[MapAnchorView] = Field(default_factory=list)


class CastEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: UUID
    name: str
    life_status: str
    location_id: UUID
    portrait_asset_id: UUID | None = None


class PresentationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    day: int
    phase: str
    absolute_index: int
    latest_run_id: UUID | None = None
    open_run_id: UUID | None = None
    run_state: str | None = None
    revision: int
    capabilities: PresentationCapabilities
    manifest: MapManifestView
    cast: list[CastEntry] = Field(default_factory=list)
    activities: list[ActivityView] = Field(default_factory=list)
    recent_event_id: UUID | None = None
    threads: list[str] = Field(default_factory=list)


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID | None = None
    kind: str = Field(min_length=1, max_length=16)
    subject_id: UUID | None = None
    style_pack_version: str = Field(default="anime-saga-v1", max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)


class JobView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID | None = None
    kind: str
    subject_id: UUID | None = None
    style_pack_version: str
    status: str
    attempt_count: int
    result_asset_id: UUID | None = None
    error: str = ""
    version: int


class AssetView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID | None = None
    kind: str
    subject_id: UUID | None = None
    content_ref: str
    mime: str
    width: int
    height: int
    style_pack_version: str
    subject_visual_version: int
    status: str
    version: int


class EnsureStarterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID


class SimulationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    absolute_index: int
    open_run_id: UUID | None = None
    open_run_state: str | None = None
    latest_run_id: UUID | None = None
    latest_run_state: str | None = None
