"""Three-phase autonomous orchestration (owned by S1-ORCH-001).

One phase runs seal -> decide -> assemble -> react -> resolve -> commit
-> narrate. Character decisions run concurrently after the snapshot
seal; every later stage is a barrier. Restarts are safe by
construction: deterministic run, snapshot, task, intent, attempt,
reaction, resolution, and scene IDs plus idempotent command keys mean
re-running a phase replays stored results instead of doubling canon.

Task-run rows are deliberately not written: S1 character work is a
synchronous in-process unit, and recovery flows through idempotent
commits, not lease healing. Task-run UUIDs still correlate graphs,
checkpoints, manifests, and model calls.

Narration never gates the next phase: a narration failure is recorded
in the report while the phase completes. S1 worlds are S1-driven; do
not mix Stage 0 advancement on the same world (both share the run
space and the clock).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from worldsim.application.commands.director import accept_decision
from worldsim.application.commands.party import recruit_companion
from worldsim.application.context.assembler import assemble, to_manifest_dict
from worldsim.application.graphs.character import (
    CHARACTER_PROMPT_VERSION,
    CharacterGraphDeps,
    build_character_graph,
    load_character_prompt,
    precheck_action,
)
from worldsim.application.graphs.director import (
    DIRECTOR_PROMPT_VERSION,
    DirectorGraphDeps,
    build_director_graph,
    load_director_prompt,
)
from worldsim.application.graphs.narrate import (
    NARRATOR_PROMPT_VERSION,
    NarratorGraphDeps,
    build_narration_graph,
    fallback_beats,
    load_narrator_prompt,
)
from worldsim.application.graphs.reaction import (
    REACTION_PROMPT_VERSION,
    ReactionGraphDeps,
    build_reaction_graph,
    load_reaction_prompt,
)
from worldsim.application.graphs.resolve import (
    RESOLVER_PROMPT_VERSION,
    ResolverGraphDeps,
    build_resolve_graph,
    load_resolver_prompt,
)
from worldsim.application.graphs.runtime import invoke
from worldsim.application.graphs.state import GraphInvocation
from worldsim.application.graphs.summary import (
    DIGEST_PROMPT_VERSION,
    SUMMARY_PROMPT_VERSION,
    SummaryGraphDeps,
    build_summary_graph,
    load_digest_prompt,
    load_summary_prompt,
)
from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
from worldsim.application.ports.model_gateway import ModelGateway
from worldsim.application.tasks.service import TaskService
from worldsim.application.tracing.gateway import TracedGateway
from worldsim.application.tracing.service import ManifestSpec, TraceService
from worldsim.application.transactions.canonical import (
    CanonicalTransaction,
    CommitRequest,
    MemorySpec,
    ObservationSpec,
    canonical_input_hash,
)
from worldsim.application.transactions.scenes import build_scene_commit, observation_spec
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.activities import Activity, effective_progress
from worldsim.domain.characters import Character
from worldsim.domain.commands import ActionIntent, CommunicateAction, MoveAction
from worldsim.domain.context import ContextEnvelope, ContextRequest, SourceCandidate
from worldsim.domain.director import (
    DIRECTOR_COOLDOWN_PHASES,
    DirectorDecision,
    should_trigger,
)
from worldsim.domain.effects import (
    AdvanceClockEffect,
    DomainEffect,
    MoveEntityEffect,
    ResourceAdjustedEffect,
    SkillProgressEffect,
)
from worldsim.domain.enums import (
    ActivityKind,
    ActivityStatus,
    EventType,
    LifeStatus,
    NarrativeStatus,
    PhaseRunState,
    ResourceKind,
    ScheduleStatus,
    Visibility,
)
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.events import WorldEvent
from worldsim.domain.ids import (
    derive_attempt_id,
    derive_combat_event_id,
    derive_intent_id,
    derive_task_id,
    new_arc_id,
    new_digest_id,
    new_hook_id,
    new_monster_id,
    new_narration_id,
    new_summary_id,
)
from worldsim.domain.memory import (
    CITE_BUMP_KEY,
    DEFAULT_CITE_BUMP,
    DEFAULT_HALF_LIFE_PHASES,
    DEFAULT_PROMOTION_MAX_PER_DAY,
    DEFAULT_PROMOTION_MIN_AGE,
    DEFAULT_PROMOTION_THRESHOLD,
    DEFAULT_RECENT_PHASES,
    DEFAULT_SALIENCE_FLOOR,
    DIGEST_SCORE,
    HALF_LIFE_PHASES_KEY,
    MAX_SALIENCE,
    PROMOTION_ENABLED_KEY,
    PROMOTION_MAX_PER_DAY_KEY,
    PROMOTION_MIN_AGE_KEY,
    PROMOTION_THRESHOLD_KEY,
    RECENT_PHASES_KEY,
    SALIENCE_FLOOR_KEY,
    MemoryDigest,
    score_salience,
)
from worldsim.domain.narration import NarrationBeat
from worldsim.domain.party import Monster
from worldsim.domain.perception import (
    Disclosure,
    FactChannel,
    FactVisibility,
    ObservableEvent,
    ObservationFact,
    PerceivedFact,
)
from worldsim.domain.phases import PhaseRun, PhaseSnapshot, SnapshotCharacter
from worldsim.domain.progress import TRAINING_STAMINA_COST
from worldsim.domain.relationships import describe
from worldsim.domain.rules.dnd import (
    DataTables,
    MonsterState,
    build_sheet_summary,
    dnd_party_prompt,
    dnd_rules_text,
    load_data,
    parse_recruit_tags,
    resolve_narration_tags,
)
from worldsim.domain.rules.perception import permitted_facts
from worldsim.domain.rules.phases import is_quiet_phase
from worldsim.domain.rules.resources import rest_recovery, restore, spend
from worldsim.domain.rules.scenes import assemble_scenes
from worldsim.domain.rules.views import WorldView
from worldsim.domain.scenes import Attempt, Intent, Reaction, Resolution, Scene
from worldsim.domain.summaries import DailySummary, day_range, fallback_text
from worldsim.domain.tasks import Lease
from worldsim.domain.time import PHASES_PER_DAY, absolute_index, utcnow
from worldsim.domain.tracing import ManifestSource

DND_DATA_DIR = "content/dnd"


#: Run states that refuse advancement (same bucket as Stage 0).
_BLOCKED_RUN_STATES = frozenset({"paused", "terminal_failed", "cancelled"})


class GatewayFactory(Protocol):
    """Role (character/reaction/resolver/narrator) to gateway."""

    def __call__(self, role: str) -> ModelGateway: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


@dataclass(frozen=True)
class SceneOutcome:
    scene_id: UUID
    event_id: UUID
    resolution_outcome: str
    narration: str


@dataclass(frozen=True)
class Stage1PhaseReport:
    run_id: UUID
    world_id: UUID
    absolute_index: int
    snapshot_id: UUID
    scenes: list[SceneOutcome] = field(default_factory=list)
    duplicate: bool = False
    quiet: bool = False


@dataclass(frozen=True)
class SealedPhase:
    """Shared snapshot plus the sealed versions and places decisions use."""

    snapshot_id: UUID
    versions: dict[str, int]
    locations: dict[UUID, UUID]


def _snapshot_hash(
    world_id: UUID, run_id: UUID, absolute: int, world_version: int, members: list[tuple[str, int]]
) -> str:
    canonical = json.dumps(
        {
            "world_id": world_id.hex,
            "run_id": run_id.hex,
            "absolute_index": absolute,
            "world_version": world_version,
            "characters": sorted(members),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _config_float(config: dict[str, object], key: str, default: float) -> float:
    """World-config float with a recorded default; wrong types fall back."""
    raw = config.get(key)
    return float(raw) if isinstance(raw, (int, float)) else default


def _config_int(config: dict[str, object], key: str, default: int) -> int:
    """World-config int with a recorded default; wrong types fall back."""
    raw = config.get(key)
    return int(raw) if isinstance(raw, int) else default


def _summarize(action: ActionIntent, names: Mapping[UUID, str]) -> str:
    if isinstance(action, MoveAction):
        return f"{names.get(action.character_id, '?')} moves"
    if isinstance(action, CommunicateAction):
        target = names.get(action.target_character_id, "?")
        return f"{names.get(action.character_id, '?')} says to {target}: {action.topic}"
    family = action.family.value
    return f"{names.get(action.character_id, '?')} {family}s"


class Stage1Orchestrator:
    """Autonomous three-phase driver over the bounded Stage 1 graphs."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        canonical: CanonicalTransaction,
        tasks: TaskService,
        traces: TraceService,
        gateway_factory: GatewayFactory,
        profiles: Mapping[str, object],
        fault_hook: Callable[[str], None] | None = None,
    ) -> None:
        self._factory = uow_factory
        self._canonical = canonical
        self._tasks = tasks
        self._traces = traces
        self._gateways = gateway_factory
        self._profiles = dict(profiles)
        self._hook = fault_hook
        self._dnd_data: DataTables | None = None

    def _fire(self, point: str) -> None:
        if self._hook is not None:
            self._hook(point)

    async def advance_phase(
        self,
        world_id: UUID,
        index: int,
        player_intents: Mapping[UUID, ActionIntent] | None = None,
    ) -> Stage1PhaseReport:
        """Advance one phase end to end (manual advancement unit)."""
        await self._tasks.reconcile()
        run_id = derive_run_id(world_id, index)
        async with self._factory() as uow:
            world = await uow.worlds.get(world_id)
            try:
                run = await uow.phases.get_run(run_id)
            except DomainError:
                run = None
        if run is not None and run.state.value == PhaseRunState.COMPLETED.value:
            return await self._duplicate_report(world_id, run_id)
        if run is not None and run.state.value in _BLOCKED_RUN_STATES:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                f"phase run is {run.state.value}; resume before advancing",
            )
        await self._probe_gate()
        current = absolute_index(world.day, world.phase)
        if current + 1 != index and current != index:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                f"phases advance consecutively: clock={current} target={index}",
            )
        try:
            async with self._factory() as uow:
                await uow.phases.create_run(
                    PhaseRun(id=run_id, world_id=world_id, absolute_index=index)
                )
                await uow.commit()
        except IntegrityError:
            pass
        await self._require_previous_complete(world_id, index)
        await self._tick(world_id, run_id, index)
        sealed = await self._seal(world_id, run_id, index)
        await self._director_phase(world_id, run_id, index, sealed)
        intents = await self._decide_all(world_id, run_id, sealed, player_intents or {})
        await self._set_state(run_id, PhaseRunState.INTENTS_COMPLETE)
        quiet = is_quiet_phase(intent.action.family for intent in intents)
        async with self._factory() as uow:
            characters = await uow.characters.list_for_world(world_id)
            locations = await uow.locations.list_for_world(world_id)
            live_world = await uow.worlds.get(world_id)
        names = {c.id: c.name for c in characters}
        view = WorldView(world=live_world, characters=characters, locations=locations)
        scenes = assemble_scenes(
            intents,
            view,
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=sealed.snapshot_id,
        )
        await self._set_state(run_id, PhaseRunState.SCENES_ASSEMBLED)
        outcomes: list[SceneOutcome] = []
        for scene in scenes:
            over_budget = await self._over_budget(world_id, run_id)
            outcomes.append(
                await self._commit_scene(
                    world_id,
                    run_id,
                    index,
                    sealed,
                    scene,
                    intents,
                    names,
                    quiet,
                    over_budget,
                )
            )
        await self._set_state(run_id, PhaseRunState.SCENES_COMMITTED)
        self._fire("after_scenes_committed")
        await self._set_state(run_id, PhaseRunState.COMPLETED)
        if index % PHASES_PER_DAY == PHASES_PER_DAY - 1:
            await self._summarize_day(world_id, run_id, index, index // PHASES_PER_DAY + 1)
            await self._promote_memories(world_id, run_id, index, index // PHASES_PER_DAY + 1)
        return Stage1PhaseReport(
            run_id=run_id,
            world_id=world_id,
            absolute_index=index,
            snapshot_id=sealed.snapshot_id,
            scenes=outcomes,
            quiet=quiet,
        )

    async def _over_budget(self, world_id: UUID, run_id: UUID) -> bool:
        """True when this run already spent its model-call budget."""
        async with self._factory() as uow:
            config = await uow.worlds.get_config(world_id)
            spent = len(await uow.traces.list_for_phase_run(run_id))
        raw = config.get("model.max_calls_per_phase")
        budget = int(raw) if isinstance(raw, int) else 32
        return spent >= max(1, budget)

    async def advance_days(
        self,
        world_id: UUID,
        start_index: int,
        day_count: int,
        player_intents: Mapping[int, Mapping[UUID, ActionIntent]] | None = None,
    ) -> list[Stage1PhaseReport]:
        """Advance whole days (ten phases each) for soak scenarios."""
        reports: list[Stage1PhaseReport] = []
        for offset in range(day_count * PHASES_PER_DAY):
            index = start_index + offset
            intents = (player_intents or {}).get(index)
            reports.append(await self.advance_phase(world_id, index, intents))
        return reports

    async def advance_three_phases(
        self,
        world_id: UUID,
        start_index: int,
        player_intents: Mapping[int, Mapping[UUID, ActionIntent]] | None = None,
    ) -> list[Stage1PhaseReport]:
        """Automatic advancement across three consecutive phases."""
        reports: list[Stage1PhaseReport] = []
        for offset in range(3):
            index = start_index + offset
            phase_players = (player_intents or {}).get(index, {})
            reports.append(await self.advance_phase(world_id, index, phase_players))
        return reports

    async def pause_phase(self, run_id: UUID) -> None:
        await self._set_state(run_id, PhaseRunState.PAUSED)

    async def resume_phase(self, run_id: UUID) -> None:
        await self._set_state(run_id, PhaseRunState.CREATED)

    async def _set_state(self, run_id: UUID, state: PhaseRunState) -> None:
        async with self._factory() as uow:
            await uow.phases.set_run_state(run_id, state.value)
            await uow.commit()

    async def _probe_gate(self) -> None:
        for role in ("character", "reaction", "resolver", "narrator"):
            probe = await self._gateways(role).probe()
            if not probe.ok:
                raise DomainError(
                    ErrorCode.PRECONDITION_FAILED,
                    f"provider unavailable for {role}: {probe.detail}",
                )

    async def _require_previous_complete(self, world_id: UUID, index: int) -> None:
        """Refuse a new phase while the prior run is not completed."""
        if index <= 1:
            return
        previous_id = derive_run_id(world_id, index - 1)
        try:
            async with self._factory() as uow:
                previous = await uow.phases.get_run(previous_id)
        except DomainError:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                f"previous phase {index - 1} never ran; advance consecutively",
            ) from None
        if previous.state.value != PhaseRunState.COMPLETED.value:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                f"previous phase {index - 1} is {previous.state.value}; reconcile first",
            )

    async def _fire_due_schedules(self, world_id: UUID, index: int) -> int:
        """Record one event per due schedule; applied rows never refire."""
        async with self._factory() as uow:
            due = await uow.schedules.list_due(world_id, index)
            for schedule in due:
                sequence = await uow.events.max_sequence(world_id) + 1
                await uow.events.append_event(
                    WorldEvent(
                        id=schedule.id,
                        world_id=world_id,
                        sequence=sequence,
                        event_type=EventType.SCHEDULE_FIRED,
                        absolute_index=index,
                        phase_run_id=derive_run_id(world_id, index),
                        participant_ids=[],
                        summary={
                            "kind": schedule.kind,
                            "due": str(schedule.due_absolute),
                        },
                    )
                )
                await uow.schedules.save(
                    schedule.model_copy(update={"status": ScheduleStatus.APPLIED}),
                    schedule.version,
                )
            await uow.commit()
            return len(due)

    async def _tick(self, world_id: UUID, run_id: UUID, index: int) -> None:
        async with self._factory() as uow:
            world = await uow.worlds.get(world_id)
            version = await uow.versions.get(world_id) or 0
        if absolute_index(world.day, world.phase) == index:
            await self._set_state(run_id, PhaseRunState.WORLD_TICKED)
            await self._fire_due_schedules(world_id, index)
            await self._advance_activities(world_id, run_id, index)
            return
        effect = AdvanceClockEffect(
            affected_ids=[world_id],
            expected_versions={str(world_id): version},
            from_index=absolute_index(world.day, world.phase),
            to_index=index,
        )
        key = f"phase_tick:{world_id.hex}:{index}"
        payload: dict[str, object] = {"absolute_index": index}
        await self._canonical.commit(
            CommitRequest(
                command_id=uuid4(),
                world_id=world_id,
                idempotency_key=key,
                actor_role="system",
                command_type="advance_phase",
                expected_versions={str(world_id): version},
                payload=payload,
                input_hash=canonical_input_hash(
                    {"key": key, "payload": payload, "effects": [effect.model_dump(mode="json")]}
                ),
                absolute_index=index,
                phase_run_id=run_id,
                event_type=EventType.WORLD_TICKED,
                effects=[effect],
            )
        )
        await self._set_state(run_id, PhaseRunState.WORLD_TICKED)
        await self._fire_due_schedules(world_id, index)
        await self._advance_activities(world_id, run_id, index)

    async def _advance_activities(self, world_id: UUID, run_id: UUID, index: int) -> int:
        """Progress due activities; completion commits once per activity.

        Progress is derived from the clock, so this only writes when an
        activity finishes. Exhausted travelers stall instead of moving.
        """
        async with self._factory() as uow:
            due = [
                activity
                for activity in await uow.activities.list_active_for_world(world_id)
                if effective_progress(activity, index) >= activity.duration_phases
            ]
        completed = 0
        for activity in due:
            if await self._complete_activity(world_id, run_id, index, activity):
                completed += 1
        return completed

    async def _complete_activity(
        self, world_id: UUID, run_id: UUID, index: int, activity: Activity
    ) -> bool:
        """Commit one activity's completion effects, then mark it done."""
        async with self._factory() as uow:
            character = await uow.characters.get(activity.character_id)
        effects: list[DomainEffect] = []
        observations: list[ObservationSpec] = []
        try:
            if activity.kind == ActivityKind.TRAVEL:
                destination = UUID(str(activity.payload["to_location_id"]))
                cost = int(activity.payload.get("stamina_cost", 0))
                effects.append(
                    MoveEntityEffect(
                        affected_ids=[character.id],
                        expected_versions={str(character.id): character.version},
                        from_location_id=character.location_id,
                        to_location_id=destination,
                    )
                )
                remaining = spend(character.stamina, cost)
                if remaining != character.stamina:
                    effects.append(
                        ResourceAdjustedEffect(
                            affected_ids=[character.id],
                            expected_versions={str(character.id): character.version},
                            resource=ResourceKind.STAMINA,
                            delta=remaining - character.stamina,
                        )
                    )
            elif activity.kind == ActivityKind.REST:
                stamina_gain, mana_gain = rest_recovery(activity.duration_phases)
                rested_stamina = restore(character.stamina, stamina_gain)
                if rested_stamina != character.stamina:
                    effects.append(
                        ResourceAdjustedEffect(
                            affected_ids=[character.id],
                            expected_versions={str(character.id): character.version},
                            resource=ResourceKind.STAMINA,
                            delta=rested_stamina - character.stamina,
                        )
                    )
                rested_mana = restore(character.mana, mana_gain)
                if rested_mana != character.mana:
                    effects.append(
                        ResourceAdjustedEffect(
                            affected_ids=[character.id],
                            expected_versions={str(character.id): character.version},
                            resource=ResourceKind.MANA,
                            delta=rested_mana - character.mana,
                        )
                    )
            elif activity.kind == ActivityKind.TRAIN:
                session = self._training_session_key(activity)
                assert session is not None
                if character.stamina < TRAINING_STAMINA_COST:
                    raise DomainError(ErrorCode.INSUFFICIENT_RESOURCE, "too tired to train")
                effects.append(
                    SkillProgressEffect(
                        affected_ids=[character.id],
                        expected_versions={str(character.id): character.version},
                        character_id=character.id,
                        skill_key=str(activity.payload.get("skill", "general")),
                        session_key=session,
                    )
                )
                effects.append(
                    ResourceAdjustedEffect(
                        affected_ids=[character.id],
                        expected_versions={str(character.id): character.version},
                        resource=ResourceKind.STAMINA,
                        delta=-TRAINING_STAMINA_COST,
                    )
                )
            elif activity.kind == ActivityKind.PATROL:
                async with self._factory() as uow:
                    origin = await uow.locations.get(character.location_id)
                observations.append(
                    ObservationSpec(
                        observer_id=character.id,
                        facts=[
                            ObservationFact(
                                key=f"patrol:{origin.name}",
                                value="quiet, no movement on the roads",
                            )
                        ],
                    )
                )
        except DomainError:
            await self._stall_activity(activity, index)
            return False
        key = f"activity_complete:{activity.id.hex}"
        try:
            await self._canonical.commit(
                CommitRequest(
                    command_id=uuid4(),
                    world_id=world_id,
                    idempotency_key=key,
                    actor_role="system",
                    command_type="complete_activity",
                    expected_versions={str(character.id): character.version},
                    payload={"activity_id": str(activity.id), "kind": activity.kind.value},
                    input_hash=canonical_input_hash(
                        {
                            "key": key,
                            "activity": str(activity.id),
                            "effects": [e.model_dump(mode="json") for e in effects],
                        }
                    ),
                    absolute_index=index,
                    phase_run_id=run_id,
                    event_type=EventType.ACTION_RESOLVED,
                    effects=effects,
                    observations=observations,
                )
            )
        except IntegrityError:
            if not await self._session_awarded(
                world_id, activity, self._training_session_key(activity)
            ):
                raise
        async with self._factory() as uow:
            try:
                await uow.activities.save(
                    activity.model_copy(update={"status": ActivityStatus.COMPLETED}),
                    activity.version,
                )
                await uow.commit()
            except DomainError:
                pass
        return True

    def _training_session_key(self, activity: Activity) -> str | None:
        if activity.kind != ActivityKind.TRAIN:
            return None
        return f"activity:{activity.id.hex}:{activity.start_absolute}"

    async def _session_awarded(
        self, world_id: UUID, activity: Activity, session_key: str | None
    ) -> bool:
        if session_key is None:
            return False
        async with self._factory() as uow:
            return await uow.progress.has_session(
                world_id,
                activity.character_id,
                str(activity.payload.get("skill", "general")),
                session_key,
            )

    async def _stall_activity(self, activity: Activity, index: int) -> None:
        """Exhausted traveler: bake progress and freeze without moving."""
        async with self._factory() as uow:
            try:
                await uow.activities.save(
                    activity.model_copy(
                        update={
                            "status": ActivityStatus.INTERRUPTED,
                            "progress_phases": effective_progress(activity, index),
                        }
                    ),
                    activity.version,
                )
                await uow.commit()
            except DomainError:
                pass

    async def _summarize_day(self, world_id: UUID, run_id: UUID, index: int, day: int) -> int:
        """Record one versioned summary per owner with same-day sources.

        Runs after midnight commits and never fails the phase: each
        owner is attempted independently, and model trouble falls back
        to structural counts. Owners with no sources get no record.
        """
        start, end = day_range(day)
        async with self._factory() as uow:
            characters = [
                c
                for c in await uow.characters.list_for_world(world_id)
                if c.life_status == LifeStatus.ALIVE
            ]
        written = 0
        for character in sorted(characters, key=lambda c: c.id.hex):
            try:
                if await self._summarize_owner(world_id, run_id, character, day, start, end):
                    written += 1
            except Exception:
                continue
        return written

    async def _summarize_owner(
        self,
        world_id: UUID,
        run_id: UUID,
        character: Character,
        day: int,
        start: int,
        end: int,
    ) -> bool:
        """Propose and store one owner's day account; False when sourceless."""
        async with self._factory() as uow:
            observations = [
                obs
                for obs in await uow.perception.observations_for_observer(character.id, 20)
                if start <= obs.created_phase_index <= end
            ]
            memories = [
                mem
                for mem in await uow.perception.memories_for_owner(character.id)
                if start <= mem.created_phase_index <= end
            ]
        if not observations and not memories:
            return False
        lines: list[str] = []
        source_ids: list[str] = []
        for obs in observations:
            for fact in obs.facts:
                lines.append(f"obs:{obs.id} {fact.key}: {fact.value}")
                source_ids.append(f"obs:{obs.id}")
        for mem in memories:
            lines.append(f"mem:{mem.id} {mem.text}")
            source_ids.append(f"mem:{mem.id}")
        task_run_id = derive_task_id(run_id, "summary", character.id)
        owner = f"s1sum:{run_id.hex[:8]}"
        await self._track_task(world_id, task_run_id, owner)
        spec = ManifestSpec(
            role="daily_summary",
            profile=self._profiles["summary"],  # type: ignore[arg-type]
            prompt_version=SUMMARY_PROMPT_VERSION,
            world_id=world_id,
            phase_run_id=run_id,
            task_run_id=task_run_id,
            actor_id=character.id,
            sources=[],
            budgets={},
            tokens={},
            dropped=[],
        )
        traced = TracedGateway(self._gateways("summary"), self._traces, spec)
        invocation = GraphInvocation(
            graph_name="daily-summary",
            graph_version="v1",
            task_run_id=task_run_id,
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=run_id,
            actor_id=character.id,
            role="daily_summary",
            profile_version=traced.profile.version,
            prompt_version=SUMMARY_PROMPT_VERSION,
            input={
                "owner_name": character.name,
                "day": day,
                "sources_text": "\n".join(lines),
                "source_ids": sorted(set(source_ids)),
            },
        )
        graph = build_summary_graph(
            SummaryGraphDeps(
                gateway=traced,
                profile=self._profiles["summary"],  # type: ignore[arg-type]
                system_template=load_summary_prompt(),
            )
        )
        try:
            result = await invoke(graph, invocation)
        except Exception:
            await self._finish_task(task_run_id, owner, False)
            return False
        await self._finish_task(task_run_id, owner, True)
        proposal: dict[str, Any] = result.get("proposal") or {}
        is_fallback = result.get("fallback", True) is True
        text = str(proposal.get("text", "")) or fallback_text(len(observations), len(memories))
        raw_cited: list[Any] = proposal.get("source_ids", [])
        cited = [str(s) for s in raw_cited] or sorted(set(source_ids))
        async with self._factory() as uow:
            taken = await uow.summaries.count_versions(world_id, character.id, day)
            await uow.summaries.add(
                DailySummary(
                    id=new_summary_id(),
                    world_id=world_id,
                    owner_id=character.id,
                    day=day,
                    text=text,
                    source_ids=cited,
                    profile_version=traced.profile.version,
                    prompt_version=SUMMARY_PROMPT_VERSION,
                    fallback=is_fallback or not proposal,
                    version=taken + 1,
                )
            )
            await self._bump_cited(uow, world_id, [str(s) for s in raw_cited])
            await uow.commit()
        return True

    async def _bump_cited(self, uow: Any, world_id: UUID, cited: list[str]) -> None:
        """Raise salience for model-cited sources only.

        Fallback-expanded citations (the whole same-day set) never
        bump: indiscriminate bumps would push every row to the cap
        within days and erase all discrimination.
        """
        if not cited:
            return
        config = await uow.worlds.get_config(world_id)
        raw_bump = config.get(CITE_BUMP_KEY)
        bump = float(raw_bump) if isinstance(raw_bump, (int, float)) else DEFAULT_CITE_BUMP
        obs_ids: list[UUID] = []
        mem_ids: list[UUID] = []
        for source_id in cited:
            kind, _, raw = source_id.partition(":")
            try:
                parsed = UUID(raw)
            except ValueError:
                continue
            if kind == "obs":
                obs_ids.append(parsed)
            elif kind == "mem":
                mem_ids.append(parsed)
        if obs_ids or mem_ids:
            await uow.perception.bump_salience(obs_ids, mem_ids, bump, MAX_SALIENCE)

    async def _promote_memories(self, world_id: UUID, run_id: UUID, index: int, day: int) -> int:
        """Compress qualifying old sources into digests; never fails the phase."""
        async with self._factory() as uow:
            config = await uow.worlds.get_config(world_id)
        if config.get(PROMOTION_ENABLED_KEY, True) is False:
            return 0
        async with self._factory() as uow:
            characters = [
                c
                for c in await uow.characters.list_for_world(world_id)
                if c.life_status == LifeStatus.ALIVE
            ]
        written = 0
        for character in sorted(characters, key=lambda c: c.id.hex):
            try:
                if await self._promote_owner(world_id, run_id, index, day, character, config):
                    written += 1
            except Exception:
                continue
        return written

    async def _promote_owner(
        self,
        world_id: UUID,
        run_id: UUID,
        index: int,
        day: int,
        character: Character,
        config: dict[str, object],
    ) -> bool:
        """Digest one owner's qualifying old sources; False when none qualify."""
        threshold = _config_float(config, PROMOTION_THRESHOLD_KEY, DEFAULT_PROMOTION_THRESHOLD)
        min_age = _config_int(config, PROMOTION_MIN_AGE_KEY, DEFAULT_PROMOTION_MIN_AGE)
        max_per_day = _config_int(config, PROMOTION_MAX_PER_DAY_KEY, DEFAULT_PROMOTION_MAX_PER_DAY)
        async with self._factory() as uow:
            taken = await uow.digests.count_versions(world_id, character.id, day)
            if taken >= max_per_day:
                return False
            digested = {
                str(source)
                for digest in await uow.digests.list_for_owner(world_id, character.id)
                for source in digest.source_ids
            }
            observations = await uow.perception.observations_for_observer(character.id, 100000)
            memories = await uow.perception.memories_for_owner(character.id)
        lines: list[str] = []
        source_ids: list[str] = []
        for obs in observations:
            if obs.salience < threshold or index - obs.created_phase_index < min_age:
                continue
            if f"obs:{obs.id}" in digested:
                continue
            for fact in obs.facts:
                lines.append(f"obs:{obs.id} {fact.key}: {fact.value}")
                source_ids.append(f"obs:{obs.id}")
        for mem in memories:
            if mem.salience < threshold or index - mem.created_phase_index < min_age:
                continue
            if f"mem:{mem.id}" in digested:
                continue
            lines.append(f"mem:{mem.id} {mem.text}")
            source_ids.append(f"mem:{mem.id}")
        if not lines:
            return False
        task_run_id = derive_task_id(run_id, "digest", character.id)
        owner = f"s1digest:{run_id.hex[:8]}"
        await self._track_task(world_id, task_run_id, owner)
        spec = ManifestSpec(
            role="memory_digest",
            profile=self._profiles["summary"],  # type: ignore[arg-type]
            prompt_version=DIGEST_PROMPT_VERSION,
            world_id=world_id,
            phase_run_id=run_id,
            task_run_id=task_run_id,
            actor_id=character.id,
            sources=[],
            budgets={},
            tokens={},
            dropped=[],
        )
        traced = TracedGateway(self._gateways("summary"), self._traces, spec)
        invocation = GraphInvocation(
            graph_name="memory-digest",
            graph_version="v1",
            task_run_id=task_run_id,
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=run_id,
            actor_id=character.id,
            role="memory_digest",
            profile_version=traced.profile.version,
            prompt_version=DIGEST_PROMPT_VERSION,
            input={
                "owner_name": character.name,
                "day": day,
                "sources_text": "\n".join(lines),
                "source_ids": sorted(set(source_ids)),
            },
        )
        graph = build_summary_graph(
            SummaryGraphDeps(
                gateway=traced,
                profile=self._profiles["summary"],  # type: ignore[arg-type]
                system_template=load_digest_prompt(),
            )
        )
        try:
            result = await invoke(graph, invocation)
        except Exception:
            await self._finish_task(task_run_id, owner, False)
            return False
        await self._finish_task(task_run_id, owner, True)
        proposal: dict[str, Any] = result.get("proposal") or {}
        text = str(proposal.get("text", "")) or f"Enduring traces: {len(source_ids)} older sources."
        raw_cited: list[Any] = proposal.get("source_ids", [])
        cited = [str(s) for s in raw_cited] or sorted(set(source_ids))
        async with self._factory() as uow:
            taken = await uow.digests.count_versions(world_id, character.id, day)
            await uow.digests.add(
                MemoryDigest(
                    id=new_digest_id(),
                    world_id=world_id,
                    owner_character_id=character.id,
                    text=text,
                    source_ids=cited,
                    day=day,
                    created_phase_index=index,
                    profile_version=traced.profile.version,
                    prompt_version=DIGEST_PROMPT_VERSION,
                    version=taken + 1,
                )
            )
            await uow.commit()
        return True

    async def _seal(self, world_id: UUID, run_id: UUID, index: int) -> SealedPhase:
        """Seal the shared snapshot every character decides from."""
        async with self._factory() as uow:
            characters = [c for c in await uow.characters.list_for_world(world_id)]
            world_version = await uow.versions.get(world_id) or 0
        members = sorted((c.id.hex, c.version) for c in characters)
        content_hash = _snapshot_hash(world_id, run_id, index, world_version, members)
        snapshot_id = derive_snapshot_id(run_id)
        snapshot = PhaseSnapshot(
            id=snapshot_id,
            world_id=world_id,
            phase_run_id=run_id,
            absolute_index=index,
            world_version=world_version,
            characters=[
                SnapshotCharacter(character_id=c.id, version=c.version) for c in characters
            ],
            content_hash=content_hash,
        )
        try:
            async with self._factory() as uow:
                await uow.phases.add_snapshot(snapshot)
                await uow.commit()
        except IntegrityError:
            pass
        sealed_versions = {f"character:{c.id}": c.version for c in characters}
        await self._set_state(run_id, PhaseRunState.SNAPSHOT_SEALED)
        return SealedPhase(
            snapshot_id=snapshot_id,
            versions=sealed_versions,
            locations={c.id: c.location_id for c in characters},
        )

    async def _director_phase(
        self, world_id: UUID, run_id: UUID, index: int, sealed: SealedPhase
    ) -> str:
        """Run the Director when the cooldown elapsed; phases never block on it.

        The trigger is deterministic (world config); the model proposes at
        most one opportunity; validation enforces privileges and budgets.
        Every path sets DIRECTOR_COMPLETE. Outage leaves last-run
        untouched so the next phase retries; runs and rejections advance it.
        """
        async with self._factory() as uow:
            config = await uow.worlds.get_config(world_id)
            characters = await uow.characters.list_for_world(world_id)
            locations = await uow.locations.list_for_world(world_id)
            hooks = await uow.narrative.list_hooks_for_world(world_id)
            arcs = await uow.narrative.list_arcs_for_world(world_id)
        last_raw = config.get("director.last_absolute")
        last = int(last_raw) if isinstance(last_raw, int) else None
        cooldown_raw = config.get("director.cooldown_phases")
        cooldown = int(cooldown_raw) if isinstance(cooldown_raw, int) else DIRECTOR_COOLDOWN_PHASES
        if not should_trigger(index, last, cooldown):
            await self._set_state(run_id, PhaseRunState.DIRECTOR_COMPLETE)
            return "skipped"
        task_run_id = derive_task_id(run_id, "director", world_id)
        owner = f"s1dir:{run_id.hex[:8]}"
        await self._track_task(world_id, task_run_id, owner)
        known = [c.id for c in characters if c.life_status == LifeStatus.ALIVE]
        active_hooks = sum(1 for h in hooks if h.status != NarrativeStatus.CLOSED)
        active_arcs = sum(1 for a in arcs if a.status != NarrativeStatus.CLOSED)
        summary = (
            f"Phase {index}. Characters: "
            + ", ".join(c.name for c in characters)
            + ". Places: "
            + ", ".join(loc.name for loc in locations)
            + ". Open hooks: "
            + ", ".join(h.title for h in hooks if h.status != NarrativeStatus.CLOSED)
            + ". Open arcs: "
            + ", ".join(a.title for a in arcs if a.status != NarrativeStatus.CLOSED)
        )
        hook_id = new_hook_id()
        arc_id = new_arc_id()
        spec = ManifestSpec(
            role="director",
            profile=self._profiles["director"],  # type: ignore[arg-type]
            prompt_version=DIRECTOR_PROMPT_VERSION,
            world_id=world_id,
            phase_run_id=run_id,
            task_run_id=task_run_id,
            actor_id=world_id,
            sources=[],
            budgets={},
            tokens={},
            dropped=[],
        )
        traced = TracedGateway(self._gateways("director"), self._traces, spec)
        invocation = GraphInvocation(
            graph_name="director-proposal",
            graph_version="v1",
            task_run_id=task_run_id,
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=sealed.snapshot_id,
            role="director",
            profile_version=traced.profile.version,
            prompt_version=DIRECTOR_PROMPT_VERSION,
            input={
                "world_summary": summary,
                "trigger_ok": True,
                "trigger_reason": "cooldown elapsed",
                "known_character_ids": [str(c) for c in known],
                "active_hooks": active_hooks,
                "active_arcs": active_arcs,
                "hook_id": str(hook_id),
                "arc_id": str(arc_id),
                "world_id": str(world_id),
            },
        )
        graph = build_director_graph(
            DirectorGraphDeps(
                gateway=traced,
                profile=self._profiles["director"],  # type: ignore[arg-type]
                system_template=load_director_prompt(),
            )
        )
        try:
            result = await invoke(graph, invocation)
        except Exception:
            await self._finish_task(task_run_id, owner, False)
            await self._set_state(run_id, PhaseRunState.DIRECTOR_COMPLETE)
            return "unavailable"
        await self._finish_task(task_run_id, owner, True)
        decision = DirectorDecision.model_validate(result.get("decision") or {})
        status = str(result.get("status", "noop"))
        async with self._factory() as uow:
            await accept_decision(
                uow,
                world_id,
                decision,
                "system",
                f"director:{run_id.hex}:{index}",
                index,
            )
        await self._set_state(run_id, PhaseRunState.DIRECTOR_COMPLETE)
        if decision.accepted:
            return "proposed"
        return status

    async def _decide_all(
        self,
        world_id: UUID,
        run_id: UUID,
        sealed: SealedPhase,
        player_intents: Mapping[UUID, ActionIntent],
    ) -> list[Intent]:
        """Concurrent character decisions after the snapshot seal (barrier)."""
        async with self._factory() as uow:
            characters = [
                c
                for c in await uow.characters.list_for_world(world_id)
                if c.life_status == LifeStatus.ALIVE
            ]
            locations = await uow.locations.list_for_world(world_id)
        known = [str(c.id) for c in characters]
        place_ids = [str(loc.id) for loc in locations]
        decisions = await asyncio.gather(
            *(
                self._decide_one(
                    world_id, run_id, sealed, character, known, place_ids, player_intents
                )
                for character in sorted(characters, key=lambda c: c.id.hex)
            )
        )
        return list(decisions)

    async def _decide_one(
        self,
        world_id: UUID,
        run_id: UUID,
        sealed: SealedPhase,
        character: Character,
        known: list[str],
        place_ids: list[str],
        player_intents: Mapping[UUID, ActionIntent],
    ) -> Intent:
        task_run_id = derive_task_id(run_id, "character", character.id)
        owner = f"s1char:{run_id.hex[:8]}"
        await self._track_task(world_id, task_run_id, owner)
        player_action = player_intents.get(character.id)
        if player_action is not None:
            denial = precheck_action(
                player_action,
                known_character_ids=frozenset(known),
                location_ids=frozenset(place_ids),
            )
            if denial is not None:
                await self._finish_task(task_run_id, owner, False)
                raise DomainError(ErrorCode.VALIDATION_FAILED, f"player intent rejected: {denial}")
            intent = Intent(
                id=derive_intent_id(world_id, sealed.snapshot_id, character.id),
                world_id=world_id,
                snapshot_id=sealed.snapshot_id,
                phase_run_id=run_id,
                author_character_id=character.id,
                action=player_action,
                idempotency_key=f"player:{task_run_id}",
            )
            await self._finish_task(task_run_id, owner, True)
            return intent
        envelope, included, excluded = await self._context_for(
            world_id, run_id, sealed.snapshot_id, character
        )
        sources, dropped = to_manifest_dict(included, excluded)
        spec = ManifestSpec(
            role="character_decision",
            profile=self._profiles["character"],  # type: ignore[arg-type]
            prompt_version=CHARACTER_PROMPT_VERSION,
            world_id=world_id,
            phase_run_id=run_id,
            task_run_id=task_run_id,
            actor_id=character.id,
            sources=sources,
            budgets={},
            tokens={"total": envelope.total_estimated_tokens},
            dropped=dropped,
        )
        traced = TracedGateway(self._gateways("character"), self._traces, spec)
        invocation = GraphInvocation(
            graph_name="character-decision",
            graph_version="v1",
            task_run_id=task_run_id,
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=sealed.snapshot_id,
            actor_id=character.id,
            context_manifest_id=envelope.manifest_id,
            role="character_decision",
            profile_version=traced.profile.version,
            prompt_version=CHARACTER_PROMPT_VERSION,
            input={
                "rendered_context": envelope.rendered,
                "actor_alive": True,
                "known_character_ids": known,
                "location_ids": place_ids,
            },
        )
        graph = build_character_graph(
            CharacterGraphDeps(
                gateway=traced,
                profile=self._profiles["character"],  # type: ignore[arg-type]
                system_template=load_character_prompt(),
            )
        )
        result = await invoke(graph, invocation)
        intent = Intent.model_validate(result["proposal"]["intent"])
        await self._finish_task(task_run_id, owner, True)
        return intent

    async def _track_task(self, world_id: UUID, task_id: UUID, owner: str) -> None:
        """Audit-only task row for a character decision (recovery stays with commits)."""
        async with self._factory() as uow:
            key = f"s1char:{task_id.hex}"
            existing = await uow.tasks.find_by_key(world_id, key)
            if existing is None:
                try:
                    await uow.tasks.create(task_id, world_id, "character_decision", key)
                    await uow.commit()
                except IntegrityError:
                    await uow.rollback()
            await uow.tasks.claim(
                task_id,
                owner,
                Lease(
                    owner=owner,
                    claimed_at=utcnow(),
                    expires_at=utcnow() + timedelta(seconds=60),
                    attempt=1,
                    max_attempts=3,
                    input_version=1,
                    idempotency_key=f"s1char:{task_id.hex}",
                ),
            )
            await uow.commit()

    async def _finish_task(self, task_id: UUID, owner: str, ok: bool) -> None:
        async with self._factory() as uow:
            await uow.tasks.finish(task_id, owner, "succeeded" if ok else "dead_letter")
            await uow.commit()

    async def _context_for(
        self, world_id: UUID, run_id: UUID, snapshot_id: UUID, character: Character
    ) -> tuple[ContextEnvelope, list[ManifestSource], list[ManifestSource]]:
        """Perspective candidates for one character (filters before ranking)."""
        async with self._factory() as uow:
            card = await uow.characters.get_card(character.id, character.card_version)
            place = await uow.locations.get(character.location_id)
            config = await uow.worlds.get_config(world_id)
            _day, _phase, now_index = await uow.worlds.get_clock(world_id)
            half_life = _config_int(config, HALF_LIFE_PHASES_KEY, DEFAULT_HALF_LIFE_PHASES)
            recent_phases = _config_int(config, RECENT_PHASES_KEY, DEFAULT_RECENT_PHASES)
            floor = _config_float(config, SALIENCE_FLOOR_KEY, DEFAULT_SALIENCE_FLOOR)
            since = max(0, now_index - recent_phases)
            observations = await uow.perception.observations_for_observer(
                character.id, 100000, since_phase_index=since, min_salience=floor
            )
            memories = await uow.perception.memories_for_owner(
                character.id, since_phase_index=since, min_salience=floor
            )

            relationships = await uow.relationships.list_for_character(world_id, character.id)
            digests = await uow.digests.list_for_owner(world_id, character.id)
            names = {c.id: c.name for c in await uow.characters.list_for_world(world_id)}
        candidates = [
            SourceCandidate(
                source_id=f"card:{character.id}",
                data_class="identity",
                visibility=Visibility.PRIVATE,
                owner_id=character.id,
                text=(
                    f"{card.name}. {card.appearance} {card.personality} {card.background}".strip()
                ),
                score=3.0,
            ),
            SourceCandidate(
                source_id=f"place:{place.id}",
                data_class="surroundings",
                visibility=Visibility.PUBLIC,
                text=(
                    f"{place.name} {place.region}. Routes: "
                    + ", ".join(str(r.destination_location_id) for r in place.routes)
                ),
                score=2.0,
            ),
            SourceCandidate(
                source_id=f"state:{character.id}",
                data_class="own_state",
                visibility=Visibility.PRIVATE,
                owner_id=character.id,
                text=(
                    f"stamina {character.stamina}, mana {character.mana}, "
                    f"status {character.life_status.value}, "
                    f"conditions {','.join(character.conditions) or 'none'}"
                ),
                score=2.0,
            ),
        ]
        for obs in observations:
            for fact in obs.facts:
                candidates.append(
                    SourceCandidate(
                        source_id=f"obs:{obs.id}:{fact.key}",
                        data_class="observations",
                        visibility=Visibility.PRIVATE,
                        owner_id=character.id,
                        text=f"{fact.key}: {fact.value}",
                        score=score_salience(
                            obs.salience, now_index - obs.created_phase_index, half_life
                        ),
                        created_phase_index=obs.created_phase_index,
                    )
                )
        for relationship in relationships:
            outgoing = relationship.source_id == character.id
            other = relationship.target_id if outgoing else relationship.source_id
            candidates.append(
                SourceCandidate(
                    source_id=f"rel:{relationship.id}",
                    data_class="relationships",
                    visibility=Visibility.PRIVATE,
                    owner_id=relationship.source_id,
                    text=describe(relationship, names.get(other, other.hex[:8])),
                    score=1.5,
                )
            )
        for memory in memories:
            candidates.append(
                SourceCandidate(
                    source_id=f"mem:{memory.id}",
                    data_class="memories",
                    visibility=memory.visibility,
                    owner_id=character.id,
                    text=memory.text,
                    score=score_salience(
                        memory.salience, now_index - memory.created_phase_index, half_life
                    ),
                    created_phase_index=memory.created_phase_index,
                )
            )
        for digest in digests:
            candidates.append(
                SourceCandidate(
                    source_id=f"digest:{digest.id}",
                    data_class="memories",
                    visibility=Visibility.PRIVATE,
                    owner_id=character.id,
                    text=digest.text,
                    score=DIGEST_SCORE,
                    created_phase_index=digest.created_phase_index,
                )
            )
        request = ContextRequest(
            role="character_decision",
            actor_id=character.id,
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=snapshot_id,
            purpose="decide next intent",
        )
        envelope, included, excluded = assemble(request, candidates)
        return envelope, included, excluded

    async def _commit_scene(
        self,
        world_id: UUID,
        run_id: UUID,
        index: int,
        sealed: SealedPhase,
        scene: Scene,
        intents: list[Intent],
        names: Mapping[UUID, str],
        quiet: bool = False,
        over_budget: bool = False,
    ) -> SceneOutcome:
        """React, resolve, commit, and narrate one scene (sequential barrier)."""
        members = [i for i in intents if i.id in scene.intent_ids]
        attempts = [
            Attempt(
                id=derive_attempt_id(i.id),
                world_id=world_id,
                intent_id=i.id,
                scene_id=scene.id,
                actor_character_id=i.author_character_id,
                observable_summary=_summarize(i.action, names),
            )
            for i in sorted(members, key=lambda x: str(x.id))
        ]
        reactions = await self._react_all(world_id, run_id, sealed, scene, attempts, names)
        resolution, live_versions = await self._resolve_scene(
            world_id, run_id, sealed, scene, members
        )
        observations, memories = self._perceive_scene(world_id, sealed, scene, members, names)
        # Only the aggregates this scene mutates enter the version check,
        # pinned to the versions the resolver just validated.
        touched = {
            key.split(":", 1)[-1]: live_versions[key]
            for key in scene.mutable_aggregate_ids
            if key in live_versions
        }
        result = await self._canonical.commit(
            build_scene_commit(
                command_id=uuid4(),
                scene=scene,
                intents=members,
                attempts=attempts,
                reactions=reactions,
                resolution=resolution,
                effects=list(resolution.effects),
                expected_versions=touched,
                absolute_index=index,
                observations=observations,
                memories=memories,
            )
        )
        self._fire("before_narration")
        narration = await self._narrate_scene(
            world_id, run_id, scene, result.event_id, quiet, over_budget
        )
        return SceneOutcome(
            scene_id=scene.id,
            event_id=result.event_id,
            resolution_outcome=resolution.outcome.value,
            narration=narration,
        )

    async def _react_all(
        self,
        world_id: UUID,
        run_id: UUID,
        sealed: SealedPhase,
        scene: Scene,
        attempts: list[Attempt],
        names: Mapping[UUID, str],
    ) -> list[Reaction]:
        """One bounded reaction graph per eligible reactor (sequential)."""
        reactions: list[Reaction] = []
        participant_ids = [str(p.character_id) for p in scene.participants]
        for attempt in attempts:
            for participant in scene.participants:
                reactor_id = participant.character_id
                if reactor_id == attempt.actor_character_id:
                    continue
                reaction = await self._react_one(
                    world_id,
                    run_id,
                    sealed,
                    scene,
                    attempt,
                    reactor_id,
                    participant_ids,
                    names,
                )
                if reaction is not None:
                    reactions.append(reaction)
        return reactions

    async def _react_one(
        self,
        world_id: UUID,
        run_id: UUID,
        sealed: SealedPhase,
        scene: Scene,
        attempt: Attempt,
        reactor_id: UUID,
        participant_ids: list[str],
        names: Mapping[UUID, str],
    ) -> Reaction | None:
        async with self._factory() as uow:
            reactor = await uow.characters.get(reactor_id)
            locations = await uow.locations.list_for_world(world_id)
        envelope, included, excluded = await self._context_for(
            world_id, run_id, sealed.snapshot_id, reactor
        )
        task_run_id = derive_task_id(run_id, "reaction", reactor_id)
        sources, dropped = to_manifest_dict(included, excluded)
        spec = ManifestSpec(
            role="reaction",
            profile=self._profiles["reaction"],  # type: ignore[arg-type]
            prompt_version=REACTION_PROMPT_VERSION,
            world_id=world_id,
            phase_run_id=run_id,
            task_run_id=task_run_id,
            actor_id=reactor_id,
            sources=sources,
            budgets={},
            tokens={"total": envelope.total_estimated_tokens},
            dropped=dropped,
        )
        traced = TracedGateway(self._gateways("reaction"), self._traces, spec)
        invocation = GraphInvocation(
            graph_name="reaction",
            graph_version="v1",
            task_run_id=task_run_id,
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=sealed.snapshot_id,
            scene_id=scene.id,
            actor_id=reactor_id,
            context_manifest_id=envelope.manifest_id,
            role="reaction",
            profile_version=traced.profile.version,
            prompt_version=REACTION_PROMPT_VERSION,
            input={
                "reactor_context": envelope.rendered,
                "observable_summary": attempt.observable_summary,
                "reactor_alive": True,
                "reactor_location_id": str(reactor.location_id),
                "event_location_id": str(sealed.locations.get(attempt.actor_character_id)),
                "participant_ids": participant_ids,
                "known_character_ids": [str(c) for c in sealed.locations],
                "location_ids": [str(loc.id) for loc in locations],
                "beats_remaining": scene.beat_budget,
                "attempt_id": str(attempt.id),
                "attempt_actor_id": str(attempt.actor_character_id),
            },
        )
        graph = build_reaction_graph(
            ReactionGraphDeps(
                gateway=traced,
                profile=self._profiles["reaction"],  # type: ignore[arg-type]
                system_template=load_reaction_prompt(),
            )
        )
        result = await invoke(graph, invocation)
        if not result["proposal"]["reacted"]:
            return None
        return Reaction.model_validate(result["proposal"]["reaction"])

    async def _resolve_scene(
        self,
        world_id: UUID,
        run_id: UUID,
        sealed: SealedPhase,
        scene: Scene,
        members: list[Intent],
    ) -> tuple[Resolution, dict[str, int]]:
        """Hybrid resolution with an audited resolver call when ambiguous."""

        async with self._factory() as uow:
            characters = await uow.characters.list_for_world(world_id)
            locations = await uow.locations.list_for_world(world_id)
        live_versions = {f"character:{c.id}": c.version for c in characters}
        task_run_id = derive_task_id(run_id, "resolver", scene.id)
        spec = ManifestSpec(
            role="resolver",
            profile=self._profiles["resolver"],  # type: ignore[arg-type]
            prompt_version=RESOLVER_PROMPT_VERSION,
            world_id=world_id,
            phase_run_id=run_id,
            task_run_id=task_run_id,
            sources=[],
            budgets={},
            tokens={},
            dropped=[],
        )
        traced = TracedGateway(self._gateways("resolver"), self._traces, spec)
        invocation = GraphInvocation(
            graph_name="resolve",
            graph_version="v1",
            task_run_id=task_run_id,
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=sealed.snapshot_id,
            scene_id=scene.id,
            role="resolver",
            profile_version=traced.profile.version,
            prompt_version=RESOLVER_PROMPT_VERSION,
            input={
                "intents_json": [i.model_dump(mode="json") for i in members],
                "characters_json": [c.model_dump(mode="json") for c in characters],
                "locations_json": [loc.model_dump(mode="json") for loc in locations],
                "expected_versions": live_versions,
            },
        )
        graph = build_resolve_graph(
            ResolverGraphDeps(
                gateway=traced,
                profile=self._profiles["resolver"],  # type: ignore[arg-type]
                system_template=load_resolver_prompt(),
            )
        )
        result = await invoke(graph, invocation)
        return Resolution.model_validate(result["proposal"]["resolution"]), live_versions

    def _perceive_scene(
        self,
        world_id: UUID,
        sealed: SealedPhase,
        scene: Scene,
        members: list[Intent],
        names: Mapping[UUID, str],
    ) -> tuple[list[ObservationSpec], list[MemorySpec]]:
        participant_ids = [p.character_id for p in scene.participants]
        events: list[ObservableEvent] = []
        for intent in sorted(members, key=lambda i: str(i.id)):
            facts = [
                PerceivedFact(
                    key=f"attempt:{intent.action.family.value}",
                    value=_summarize(intent.action, names),
                    visibility=FactVisibility.SCENE,
                    channel=FactChannel.SIGHT,
                )
            ]
            disclosures: list[Disclosure] = []
            if isinstance(intent.action, CommunicateAction):
                disclosures.append(
                    Disclosure(
                        fact_key=f"attempt:{intent.action.family.value}",
                        recipient_ids=[intent.action.target_character_id],
                    )
                )
            events.append(
                ObservableEvent(
                    event_id=uuid4(),
                    world_id=world_id,
                    location_id=sealed.locations[intent.author_character_id],
                    participant_ids=participant_ids,
                    facts=facts,
                    disclosures=disclosures,
                )
            )
        observations: list[tuple[UUID, PerceivedFact]] = []
        for observer in sorted(set(participant_ids) | set(sealed.locations)):
            observer_place = sealed.locations.get(observer)
            for event in events:
                for fact in permitted_facts(event, observer, observer_place):
                    observations.append((observer, fact))
        specs = [observation_spec(observer, [fact]) for observer, fact in observations]
        memories: list[MemorySpec] = []
        for participant in sorted(set(participant_ids)):
            own = next(
                (
                    index
                    for index, (observer, _fact) in enumerate(observations)
                    if observer == participant
                ),
                None,
            )
            own_summary = next(
                (
                    _summarize(i.action, names)
                    for i in members
                    if i.author_character_id == participant
                ),
                "the scene unfolds",
            )
            memories.append(
                MemorySpec(
                    owner_id=participant,
                    text=f"{names.get(participant, '?')} remembers: {own_summary}",
                    observation_index=own,
                )
            )
        return specs, memories

    def _dnd_tables(self) -> DataTables:
        """Vendored SRD tables, loaded once (only when a party exists)."""
        if self._dnd_data is None:
            self._dnd_data = load_data(DND_DATA_DIR)
        return self._dnd_data

    async def _roster_present(self, world_id: UUID) -> bool:
        async with self._factory() as uow:
            return bool(await uow.party.list_for_world(world_id))

    async def _narrate_scene(
        self,
        world_id: UUID,
        run_id: UUID,
        scene: Scene,
        event_id: UUID,
        quiet: bool = False,
        over_budget: bool = False,
    ) -> str:
        """Narrate one committed scene; failures never fail the phase.

        Quiet non-party phases and over-budget phases skip the model
        and store structured fallback beats directly: same canon, no
        call. Party scenes always narrate because combat and recruit
        tags live in model-authored beats.
        """
        async with self._factory() as uow:
            existing = await uow.scenes.narrations_for_event(event_id)
            observations = await uow.perception.observations_for_event(event_id)
            participants = [
                str(p.character_id) for p in (await uow.scenes.get_scene(scene.id)).participants
            ]
            roster = await uow.party.list_for_world(world_id)
        if existing:
            return "skipped"
        facts = [
            {"key": fact.key, "value": fact.value} for obs in observations for fact in obs.facts
        ]
        dnd_context: str | None = None
        dnd_sources: list[ManifestSource] = []
        if roster:
            tables = self._dnd_tables()
            summaries = {
                member.name_key: build_sheet_summary(tables, member.sheet) for member in roster
            }
            facts.extend(
                {"key": f"dnd-sheet:{key}", "value": summary} for key, summary in summaries.items()
            )
            dnd_context = (
                dnd_party_prompt([m.sheet for m in roster], tables) + "\n" + dnd_rules_text()
            )
            dnd_sources = [
                ManifestSource(
                    source_id=f"dnd-sheet:{member.name_key}",
                    kind="dnd-sheet",
                    visibility=Visibility.PUBLIC,
                    reason="party sheet",
                )
                for member in roster
            ]
        task_run_id = derive_task_id(run_id, "narrator", scene.id)
        spec = ManifestSpec(
            role="narrator",
            profile=self._profiles["narrator"],  # type: ignore[arg-type]
            prompt_version=NARRATOR_PROMPT_VERSION,
            world_id=world_id,
            phase_run_id=run_id,
            task_run_id=task_run_id,
            sources=dnd_sources,
            budgets={},
            tokens={},
            dropped=[],
        )
        traced = TracedGateway(self._gateways("narrator"), self._traces, spec)
        invocation = GraphInvocation(
            graph_name="narrate",
            graph_version="v1",
            task_run_id=task_run_id,
            world_id=world_id,
            phase_run_id=scene.phase_run_id,
            snapshot_id=scene.snapshot_id,
            scene_id=scene.id,
            role="narrator",
            profile_version=traced.profile.version,
            prompt_version=NARRATOR_PROMPT_VERSION,
            input={
                "event_id": str(event_id),
                "event_committed": True,
                "audience_ids": participants,
                "visible_facts": facts,
                "beats_budget": scene.beat_budget,
                "dnd_context": dnd_context,
            },
        )
        roster_pre = await self._roster_present(world_id)
        if over_budget or (quiet and not roster_pre):
            async with self._factory() as uow:
                for beat in fallback_beats(
                    world_id=world_id,
                    scene_id=scene.id,
                    event_id=event_id,
                    visible_facts=facts,
                    beats_budget=scene.beat_budget,
                ):
                    await uow.scenes.save_narration(beat)
                await uow.commit()
            return "fallback"
        try:
            graph = build_narration_graph(
                NarratorGraphDeps(
                    gateway=traced,
                    profile=self._profiles["narrator"],  # type: ignore[arg-type]
                    system_template=load_narrator_prompt(),
                )
            )
            result = await invoke(graph, invocation)
        except Exception:
            return "failed"
        async with self._factory() as uow:
            for beat_json in result["proposal"]["beats"]:
                await uow.scenes.save_narration(NarrationBeat.model_validate(beat_json))
            await uow.commit()
            beat_texts = [
                str(beat_json.get("text", "")) for beat_json in result["proposal"]["beats"]
            ]
        await self._recruit_from_narration(world_id, "\n".join(beat_texts))
        await self._resolve_combat_tags(world_id, run_id, scene, event_id, beat_texts)
        return "narrated" if not result["proposal"]["fallback"] else "fallback"

    async def _recruit_from_narration(self, world_id: UUID, text: str) -> list[str]:
        """Resolve RECRUIT tags from narration; replays for members are no-ops."""
        tags = parse_recruit_tags(text)
        if not tags:
            return []
        async with self._factory() as uow:
            if not await uow.party.list_for_world(world_id):
                return []
        joined: list[str] = []
        tables = self._dnd_tables()
        async with self._factory() as uow:
            for tag in tags:
                result = await recruit_companion(uow, tables, world_id, tag.name, tag.desc)
                if result.joined:
                    joined.append(result.member.name)
        return joined

    async def _resolve_combat_tags(
        self,
        world_id: UUID,
        run_id: UUID,
        scene: Scene,
        event_id: UUID,
        beat_texts: list[str],
    ) -> str:
        """Roll tagged combat, persist HP, and record one combat event plus beats.

        Runs after narration is saved and never fails the phase: domain
        contention returns "failed" while unexpected errors stay loud.
        Rolls seed from the narrated event, so the same narration replays
        to the same numbers; the combat event ID derives from it too, so
        a double resolve collides instead of double-applying HP.
        """
        text = "\n".join(beat_texts)
        async with self._factory() as uow:
            roster = await uow.party.list_for_world(world_id)
            if not roster:
                return "no-party"
            live_monsters = await uow.monsters.list_for_world(world_id)
            run = await uow.phases.get_run(run_id)
        tables = self._dnd_tables()
        digest = hashlib.sha256(str(event_id).encode()).digest()[:8]
        seed = int.from_bytes(digest, "big") & ((1 << 63) - 1)
        try:
            for _ in range(2):
                report = resolve_narration_tags(
                    text,
                    [member.sheet for member in roster],
                    tables,
                    random.Random(seed).random,
                    live=[
                        MonsterState(
                            key=monster.name_key,
                            name=monster.name,
                            hp_current=monster.hp_current,
                            hp_max=monster.hp_max,
                            ac=monster.ac,
                        )
                        for monster in live_monsters
                    ],
                )
                if not report.outcomes and not report.unresolved:
                    return "no-tags"
                try:
                    async with self._factory() as uow:
                        by_key = {member.name_key: member for member in roster}
                        working = {
                            key: member.sheet.model_copy(deep=True)
                            for key, member in by_key.items()
                        }
                        for key, current in report.hp.items():
                            hit_points = working[key].hp
                            if hit_points is not None:
                                hit_points.current = current
                        for key, conditions in report.conditions.items():
                            working[key].conditions = list(conditions)
                        touched = set(report.hp) | set(report.conditions)
                        for key in sorted(touched):
                            member = by_key[key]
                            await uow.party.save_sheet(member.id, working[key], member.version)
                        pools = {monster.name_key: monster for monster in live_monsters}
                        for key in sorted(report.monsters):
                            result = report.monsters[key]
                            pool = pools.get(key)
                            if pool is None:
                                await uow.monsters.add(
                                    Monster(
                                        id=new_monster_id(),
                                        world_id=world_id,
                                        name_key=key,
                                        name=result.name,
                                        hp_current=result.hp_current,
                                        hp_max=result.hp_max,
                                        ac=result.ac,
                                    )
                                )
                            elif (
                                pool.hp_current != result.hp_current
                                or pool.hp_max != result.hp_max
                                or result.spawned
                            ):
                                await uow.monsters.save_hp(pool.id, result.hp_current, pool.version)
                        combat_id = derive_combat_event_id(event_id)
                        sequence = await uow.events.max_sequence(world_id) + 1
                        involved = {
                            by_key[key].id
                            for outcome in report.outcomes
                            for key in (outcome.attacker_key, outcome.target_key)
                            if key is not None and key in by_key
                        }
                        log = " | ".join(o.text for o in report.outcomes)[:512]
                        await uow.events.append_event(
                            WorldEvent(
                                id=combat_id,
                                world_id=world_id,
                                sequence=sequence,
                                event_type=EventType.ACTION_RESOLVED,
                                absolute_index=run.absolute_index,
                                phase_run_id=run_id,
                                participant_ids=sorted(involved, key=str),
                                summary={
                                    "tags": str(len(report.outcomes)),
                                    "unresolved": str(len(report.unresolved)),
                                },
                                random_seed=seed,
                                random_algorithm="seeded-d20-v1",
                                random_result=log or None,
                            )
                        )
                        for beat in report.beats:
                            await uow.scenes.save_narration(
                                NarrationBeat(
                                    id=new_narration_id(),
                                    world_id=world_id,
                                    scene_id=scene.id,
                                    source_event_id=combat_id,
                                    cited_fact_keys=list(beat.cited),
                                    text=beat.text,
                                )
                            )
                        await uow.commit()
                    return "resolved"
                except DomainError as exc:
                    if exc.code is not ErrorCode.VERSION_CONFLICT:
                        raise
                    async with self._factory() as uow:
                        roster = await uow.party.list_for_world(world_id)
            return "failed"
        except DomainError:
            return "failed"

    async def _duplicate_report(self, world_id: UUID, run_id: UUID) -> Stage1PhaseReport:
        """Rebuild the stored report for a completed run (no new canon)."""
        async with self._factory() as uow:
            run = await uow.phases.get_run(run_id)
            snapshot = await uow.phases.get_snapshot(derive_snapshot_id(run_id))
            characters = [c.character_id for c in snapshot.characters]
            intents = [
                await uow.scenes.get_intent(derive_intent_id(world_id, snapshot.id, c))
                for c in characters
            ]
            view_world = await uow.worlds.get(world_id)
            view_chars = await uow.characters.list_for_world(world_id)
            view_locs = await uow.locations.list_for_world(world_id)
        scenes = assemble_scenes(
            intents,
            WorldView(world=view_world, characters=view_chars, locations=view_locs),
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=snapshot.id,
        )
        outcomes: list[SceneOutcome] = []
        async with self._factory() as uow:
            for scene in scenes:
                stored = await uow.scenes.get_scene(scene.id)
                assert stored.event_id is not None
                resolution = await uow.scenes.get_resolution(scene.id)
                beats = await uow.scenes.narrations_for_event(stored.event_id)
                outcomes.append(
                    SceneOutcome(
                        scene_id=scene.id,
                        event_id=stored.event_id,
                        resolution_outcome=resolution.outcome.value,
                        narration="narrated" if beats else "missing",
                    )
                )
        return Stage1PhaseReport(
            run_id=run_id,
            world_id=world_id,
            absolute_index=run.absolute_index,
            snapshot_id=snapshot.id,
            scenes=outcomes,
            duplicate=True,
            quiet=is_quiet_phase(intent.action.family for intent in intents),
        )
