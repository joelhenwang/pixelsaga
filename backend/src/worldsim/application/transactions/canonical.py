"""Atomic event/effect commit (owned by S0-TX-001).

One commit writes the idempotency record, the world event, ordered
effects, projections, observations, memories, and outbox messages, then
links the command to its result. Anything failing before commit leaves
no canonical rows; a retry after commit returns the stored result.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID, uuid4

from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.characters import Character
from worldsim.domain.effects import (
    AdvanceClockEffect,
    DomainEffect,
    MoveEntityEffect,
    ResourceAdjustedEffect,
    SkillProgressEffect,
)
from worldsim.domain.enums import (
    AttemptStatus,
    EffectType,
    EventType,
    IntentStatus,
    ReactionStatus,
    SceneStatus,
    Visibility,
)
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.events import CommittedEffect, WorldEvent
from worldsim.domain.ids import new_skill_id
from worldsim.domain.perception import Observation, ObservationFact, RecentMemory
from worldsim.domain.progress import (
    CharacterSkill,
    TrainingSession,
    fold_progress,
    session_gain,
)
from worldsim.domain.rules.projection import apply_character_effect, apply_world_effect
from worldsim.domain.rules.randomness import RandomEvidence
from worldsim.domain.scenes import Attempt, Intent, Reaction, Resolution, Scene
from worldsim.domain.tasks import OutboxMessage
from worldsim.domain.time import utcnow
from worldsim.domain.world import World


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


def canonical_input_hash(parts: Mapping[str, Any]) -> str:
    """Stable sha256 over normalized JSON for idempotency comparison."""
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ObservationSpec:
    observer_id: UUID
    facts: list[ObservationFact] = field(default_factory=list)


@dataclass(frozen=True)
class MemorySpec:
    owner_id: UUID
    text: str
    visibility: Visibility = Visibility.PRIVATE
    observation_index: int | None = None


@dataclass(frozen=True)
class OutboxSpec:
    kind: str
    payload: dict[str, object] = field(default_factory=dict)
    key: str = ""


@dataclass(frozen=True)
class SceneRecords:
    """Stage 1 scene layer persisted atomically with its event (S1-COMMIT-001)."""

    scene: Scene
    intents: list[Intent] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    reactions: list[Reaction] = field(default_factory=list)
    resolution: Resolution | None = None


@dataclass(frozen=True)
class CommitRequest:
    command_id: UUID
    world_id: UUID
    idempotency_key: str
    actor_role: str
    command_type: str
    expected_versions: dict[str, int]
    payload: dict[str, object]
    input_hash: str
    absolute_index: int
    phase_run_id: UUID
    event_type: EventType
    effects: list[DomainEffect]
    observations: list[ObservationSpec] = field(default_factory=list)
    memories: list[MemorySpec] = field(default_factory=list)
    outbox: list[OutboxSpec] = field(default_factory=list)
    random: RandomEvidence | None = None
    scene_records: SceneRecords | None = None


@dataclass(frozen=True)
class CommitResult:
    event_id: UUID
    sequence: int
    effect_count: int
    versions: dict[str, int]
    observation_ids: list[UUID]
    memory_ids: list[UUID]
    outbox_ids: list[UUID]
    duplicate: bool


class CanonicalTransaction:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        pre_commit_hook: Callable[[str], None] | None = None,
    ) -> None:
        self._factory = uow_factory
        self._hook = pre_commit_hook

    def _fire(self, point: str) -> None:
        if self._hook is not None:
            self._hook(point)

    async def commit(self, request: CommitRequest) -> CommitResult:
        async with self._factory() as uow:
            existing = await uow.commands.get_by_key(request.world_id, request.idempotency_key)
            if existing is not None:
                return await self._duplicate(uow, existing, request)
            try:
                await uow.commands.add(
                    command_id=request.command_id,
                    world_id=request.world_id,
                    key=request.idempotency_key,
                    actor_role=request.actor_role,
                    command_type=request.command_type,
                    expected_versions=dict(request.expected_versions),
                    payload=dict(request.payload),
                    input_hash=request.input_hash,
                )
            except DomainError as exc:
                if exc.code is not ErrorCode.IDEMPOTENCY_CONFLICT:
                    raise
                await uow.rollback()
                return await self._race_retry(request, exc)
            self._fire("after_command")
            expected = {UUID(key): value for key, value in request.expected_versions.items()}
            versions = await uow.versions.compare_and_bump(expected)
            sequence = await uow.events.max_sequence(request.world_id) + 1
            event_id = uuid4()
            await uow.events.append_event(
                WorldEvent(
                    id=event_id,
                    world_id=request.world_id,
                    sequence=sequence,
                    event_type=request.event_type,
                    absolute_index=request.absolute_index,
                    phase_run_id=request.phase_run_id,
                    source_command_id=request.command_id,
                )
            )

            for ordinal, effect in enumerate(request.effects):
                await uow.events.append_effect(
                    CommittedEffect(event_id=event_id, ordinal=ordinal, effect=effect)
                )
            self._fire("after_effects")
            if request.scene_records is not None:
                await self._persist_scene(uow, request, event_id)
                self._fire("after_scene")
            await self._project(uow, request)
            self._fire("after_projections")
            observation_ids = await self._perceive(uow, request, event_id)
            self._fire("after_perception")
            outbox_ids = await self._enqueue(uow, request, event_id)
            self._fire("after_outbox")
            memory_ids = await self._remember(uow, request, event_id, observation_ids)
            await uow.commands.set_result(request.command_id, event_id)
            await uow.commit()
            return CommitResult(
                event_id=event_id,
                sequence=sequence,
                effect_count=len(request.effects),
                versions={str(key): value for key, value in versions.items()},
                observation_ids=observation_ids,
                memory_ids=memory_ids,
                outbox_ids=outbox_ids,
                duplicate=False,
            )

    async def _duplicate(
        self, uow: UnitOfWork, command_id: UUID, request: CommitRequest
    ) -> CommitResult:
        stored_hash = await uow.commands.get_input_hash(command_id)
        if stored_hash != request.input_hash:
            raise DomainError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                f"idempotency key reused with different input: {request.idempotency_key}",
            )
        event_id = await uow.commands.get_result(command_id)
        assert event_id is not None, "completed command must link its event"
        event = await uow.events.get_event(event_id)
        effects = await uow.events.list_effects(event_id)
        return CommitResult(
            event_id=event_id,
            sequence=event.sequence,
            effect_count=len(effects),
            versions=_result_versions(effects),
            observation_ids=[
                obs.id for obs in await uow.perception.observations_for_event(event_id)
            ],
            memory_ids=[],
            outbox_ids=[],
            duplicate=True,
        )

    async def _race_retry(self, request: CommitRequest, exc: BaseException) -> CommitResult:
        async with self._factory() as uow:
            existing = await uow.commands.get_by_key(request.world_id, request.idempotency_key)
            if existing is None:
                raise exc
            return await self._duplicate(uow, existing, request)

    async def _persist_scene(self, uow: UnitOfWork, request: CommitRequest, event_id: UUID) -> None:
        """Persist the scene layer with commit-time statuses (S1-COMMIT-001)."""
        records = request.scene_records
        if records is None:
            return
        for intent in records.intents:
            await uow.scenes.save_intent(
                intent.model_copy(update={"status": IntentStatus.VALIDATED})
            )
        await uow.scenes.save_scene(
            records.scene.model_copy(
                update={"status": SceneStatus.COMMITTED, "event_id": event_id}
            ),
            event_id,
        )
        for attempt in records.attempts:
            await uow.scenes.save_attempt(
                attempt.model_copy(
                    update={"status": AttemptStatus.COMMITTED, "scene_id": records.scene.id}
                )
            )
        for reaction in records.reactions:
            await uow.scenes.save_reaction(
                reaction.model_copy(
                    update={"status": ReactionStatus.COMMITTED, "scene_id": records.scene.id}
                )
            )
        if records.resolution is not None:
            await uow.scenes.save_resolution(records.resolution)

    async def _project(self, uow: UnitOfWork, request: CommitRequest) -> None:
        # Fold every effect per aggregate, then save once: the version
        # table bumps once per commit, so rows must too. Saving per
        # effect goes stale on the second touch of one aggregate.
        worlds: dict[UUID, World] = {}
        characters: dict[UUID, Character] = {}
        clock: dict[UUID, AdvanceClockEffect] = {}
        for effect in request.effects:
            if isinstance(effect, AdvanceClockEffect):
                target = _primary_target(effect, request.world_id)
                current = worlds.get(target)
                if current is None:
                    current = await uow.worlds.get(target)
                worlds[target] = apply_world_effect(current, effect)
                clock[target] = effect
            elif isinstance(effect, SkillProgressEffect):
                await self._progress_skill(uow, request, effect)
            elif isinstance(effect, (MoveEntityEffect, ResourceAdjustedEffect)):
                target = _primary_target(effect, request.world_id)
                current = characters.get(target)
                if current is None:
                    current = await uow.characters.get(target)
                characters[target] = apply_character_effect(current, effect)
            else:
                # Observation and memory effects project no state. New effect
                # types must add a projector branch instead of landing here.
                if effect.effect_type not in (
                    EffectType.RECORD_OBSERVATION,
                    EffectType.RECORD_MEMORY,
                ):
                    raise DomainError(
                        ErrorCode.UNSUPPORTED_ACTION,
                        f"no projector for {effect.effect_type.value}",
                    )
        for target, world in worlds.items():
            await uow.worlds.save(world, request.expected_versions[str(target)])
            last = clock[target]
            assert isinstance(last, AdvanceClockEffect)
            await uow.worlds.set_clock(target, world.day, world.phase.value, last.to_index)
        for target, character in characters.items():
            await uow.characters.save_state(character, request.expected_versions[str(target)])

    async def _progress_skill(
        self, uow: UnitOfWork, request: CommitRequest, effect: SkillProgressEffect
    ) -> None:
        """Count one training session; repeats of the key add nothing."""
        progress = uow.progress
        if await progress.has_session(
            request.world_id, effect.character_id, effect.skill_key, effect.session_key
        ):
            return
        definition = await progress.ensure_skill(
            request.world_id, effect.skill_key, effect.skill_key
        )
        current = await progress.get_skill(request.world_id, effect.character_id, effect.skill_key)
        gain = session_gain(current.sessions if current else 0)
        if current is None:
            current = CharacterSkill(
                id=new_skill_id(),
                world_id=request.world_id,
                character_id=effect.character_id,
                skill_key=effect.skill_key,
                sessions=1,
                progress=fold_progress(0, gain, definition.max_progress),
            )
            await progress.add_session(
                TrainingSession(
                    id=new_skill_id(),
                    world_id=request.world_id,
                    character_id=effect.character_id,
                    skill_key=effect.skill_key,
                    session_key=effect.session_key,
                    gain=gain,
                )
            )
            await progress.add_skill(current)
            return
        await progress.add_session(
            TrainingSession(
                id=new_skill_id(),
                world_id=request.world_id,
                character_id=effect.character_id,
                skill_key=effect.skill_key,
                session_key=effect.session_key,
                gain=gain,
            )
        )
        await progress.save_skill(
            current.model_copy(
                update={
                    "sessions": current.sessions + 1,
                    "progress": fold_progress(current.progress, gain, definition.max_progress),
                }
            ),
            current.version,
        )

    async def _perceive(
        self, uow: UnitOfWork, request: CommitRequest, event_id: UUID
    ) -> list[UUID]:
        ids: list[UUID] = []
        for spec in request.observations:
            observation = Observation(
                id=uuid4(),
                world_id=request.world_id,
                event_id=event_id,
                observer_character_id=spec.observer_id,
                facts=list(spec.facts),
                created_phase_index=request.absolute_index,
            )
            await uow.perception.add_observation(observation)
            ids.append(observation.id)
        return ids

    async def _remember(
        self,
        uow: UnitOfWork,
        request: CommitRequest,
        event_id: UUID,
        observation_ids: list[UUID],
    ) -> list[UUID]:
        ids: list[UUID] = []
        for spec in request.memories:
            observation_id = None
            if spec.observation_index is not None:
                observation_id = observation_ids[spec.observation_index]
            memory = RecentMemory(
                id=uuid4(),
                world_id=request.world_id,
                owner_character_id=spec.owner_id,
                event_id=event_id,
                observation_id=observation_id,
                text=spec.text,
                visibility=spec.visibility,
                created_phase_index=request.absolute_index,
            )
            await uow.perception.add_memory(memory)
            ids.append(memory.id)
        return ids

    async def _enqueue(self, uow: UnitOfWork, request: CommitRequest, event_id: UUID) -> list[UUID]:
        ids: list[UUID] = []
        for spec in request.outbox:
            message = OutboxMessage(
                id=uuid4(),
                world_id=request.world_id,
                event_id=event_id,
                kind=spec.kind,
                payload=dict(spec.payload),
                idempotency_key=spec.key,
                created_at=utcnow(),
            )
            await uow.outbox.add(message)
            ids.append(message.id)
        return ids


def _primary_target(effect: DomainEffect, world_id: UUID) -> UUID:
    if isinstance(effect, AdvanceClockEffect):
        return world_id
    return effect.affected_ids[0]


def _result_versions(effects: list[CommittedEffect]) -> dict[str, int]:
    versions: dict[str, int] = {}
    for item in effects:
        for target in item.effect.affected_ids:
            key = str(target)
            preimage = item.effect.expected_versions.get(key, 0)
            versions[key] = max(versions.get(key, 0), preimage + 1)
    return versions
