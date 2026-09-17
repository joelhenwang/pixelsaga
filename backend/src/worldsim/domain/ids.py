"""Opaque aggregate identifiers (owned by S0-DOM-001).

IDs are UUID-compatible, immutable, and never encode mutable domain data.
See the identifier rules in 03_DOMAIN_AND_PERSISTENCE.md.
"""

from __future__ import annotations

from uuid import NAMESPACE_OID, UUID, uuid4, uuid5

WorldId = UUID
CharacterId = UUID
CardId = UUID
LocationId = UUID
RouteId = UUID
ActivityId = UUID
ScheduleId = UUID
RelationshipId = UUID
RelationshipEvidenceId = UUID
ClaimId = UUID
BeliefId = UUID
SkillId = UUID
ItemInstanceId = UUID
HookId = UUID
ArcId = UUID
SummaryId = UUID
DigestId = UUID
RoleGrantId = UUID
PhaseRunId = UUID
SnapshotId = UUID
TaskId = UUID
EventId = UUID
CommandId = UUID
ObservationId = UUID
MemoryId = UUID
OutboxId = UUID
CallId = UUID
ManifestId = UUID
IntentId = UUID
AttemptId = UUID
SceneId = UUID
ReactionId = UUID
ResolutionId = UUID
NarrationId = UUID
PartyMemberId = UUID
MonsterId = UUID
MacroRunId = UUID
MacroAggregateEffectId = UUID
MacroInterruptionId = UUID
LineageLinkId = UUID
FocusAssignmentId = UUID
EraSummaryId = UUID
EndEvidenceId = UUID


def new_world_id() -> WorldId:
    return uuid4()


def new_character_id() -> CharacterId:
    return uuid4()


def new_party_member_id() -> PartyMemberId:
    return uuid4()


def new_monster_id() -> MonsterId:
    return uuid4()


def new_card_id() -> CardId:
    return uuid4()


def new_location_id() -> LocationId:
    return uuid4()


def new_route_id() -> RouteId:
    return uuid4()


def new_activity_id() -> ActivityId:
    return uuid4()


def new_schedule_id() -> ScheduleId:
    return uuid4()


def new_relationship_id() -> RelationshipId:
    return uuid4()


def new_relationship_evidence_id() -> RelationshipEvidenceId:
    return uuid4()


def new_claim_id() -> ClaimId:
    return uuid4()


def new_belief_id() -> BeliefId:
    return uuid4()


def new_skill_id() -> SkillId:
    return uuid4()


def new_item_instance_id() -> ItemInstanceId:
    return uuid4()


def new_hook_id() -> HookId:
    return uuid4()


def new_arc_id() -> ArcId:
    return uuid4()


def new_summary_id() -> SummaryId:
    return uuid4()


def new_digest_id() -> DigestId:
    return uuid4()


def new_role_grant_id() -> RoleGrantId:
    return uuid4()


def new_phase_run_id() -> PhaseRunId:
    return uuid4()


def new_snapshot_id() -> SnapshotId:
    return uuid4()


def new_task_id() -> TaskId:
    return uuid4()


def new_event_id() -> EventId:
    return uuid4()


def new_command_id() -> CommandId:
    return uuid4()


def new_observation_id() -> ObservationId:
    return uuid4()


def new_memory_id() -> MemoryId:
    return uuid4()


def new_outbox_id() -> OutboxId:
    return uuid4()


def new_call_id() -> CallId:
    return uuid4()


def new_manifest_id() -> ManifestId:
    return uuid4()


def new_intent_id() -> IntentId:
    return uuid4()


def _derive(*parts: object) -> UUID:
    return uuid5(NAMESPACE_OID, ":".join(["worldsim", *(str(p) for p in parts)]))


def derive_intent_id(world_id: WorldId, snapshot_id: SnapshotId, author: CharacterId) -> IntentId:
    """Stable intent ID: one intent per author per snapshot (matches the DB constraint)."""
    return _derive("intent", world_id.hex, snapshot_id.hex, author.hex)


def derive_attempt_id(intent_id: IntentId) -> AttemptId:
    """Stable attempt ID: one attempt per intent."""
    return _derive("attempt", intent_id.hex)


def derive_reaction_id(attempt_id: AttemptId, reactor: CharacterId) -> ReactionId:
    """Stable reaction ID: one reaction per reactor per attempt."""
    return _derive("reaction", attempt_id.hex, reactor.hex)


def derive_resolution_id(scene_id: SceneId) -> ResolutionId:
    """Stable resolution ID: one resolution per scene."""
    return _derive("resolution", scene_id.hex)


def derive_combat_event_id(source_event_id: UUID) -> EventId:
    """Stable combat event ID: one combat record per narrated event."""
    return _derive("combat", source_event_id.hex)


def derive_task_id(run_id: PhaseRunId, role: str, actor: CharacterId) -> TaskId:
    """Stable task-run ID: restarts resume the same graph thread."""
    return _derive("task", run_id.hex, role, actor.hex)


def derive_macro_run_id(
    world_id: WorldId, start_absolute: int, end_absolute: int, resolution: str
) -> MacroRunId:
    """Stable macro run ID: repeating a period replays the same run, never duplicates."""
    return _derive("macro-run", world_id.hex, start_absolute, end_absolute, resolution)


def derive_lineage_child_id(schedule_id: ScheduleId) -> CharacterId:
    """Stable birth identity: one child per birth schedule, never a second."""
    return _derive("lineage-child", schedule_id.hex)


def derive_macro_effect_id(
    run_id: MacroRunId, kind: str, event_id: EventId
) -> MacroAggregateEffectId:
    """Stable aggregate ID: resuming a period re-links its events, never duplicates rows."""
    return _derive("macro-effect", run_id.hex, kind, event_id.hex)


def new_attempt_id() -> AttemptId:
    return uuid4()


def new_scene_id() -> SceneId:
    return uuid4()


def new_reaction_id() -> ReactionId:
    return uuid4()


def new_macro_run_id() -> MacroRunId:
    return uuid4()


def new_macro_aggregate_effect_id() -> MacroAggregateEffectId:
    return uuid4()


def new_macro_interruption_id() -> MacroInterruptionId:
    return uuid4()


def new_lineage_link_id() -> LineageLinkId:
    return uuid4()


def new_focus_assignment_id() -> FocusAssignmentId:
    return uuid4()


def new_era_summary_id() -> EraSummaryId:
    return uuid4()


def new_end_evidence_id() -> EndEvidenceId:
    return uuid4()


def new_resolution_id() -> ResolutionId:
    return uuid4()


def new_narration_id() -> NarrationId:
    return uuid4()
