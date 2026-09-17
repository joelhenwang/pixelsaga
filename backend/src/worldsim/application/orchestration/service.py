"""Deterministic phase runner and reconciler (owned by S0-ORCH-001).

One advance heals before it ticks: a run whose tick committed before a
crash is sealed and finalized first, then the next index advances. Every
step is idempotent (deterministic run, command, task-key, and snapshot
IDs plus the canonical transaction's duplicate path), so resuming after
a crash is simply running ``advance_world`` again: no duplicate phase,
event, effect, or snapshot can result.

Pause is a pre-commit gate only: a paused run blocks advancement until
``resume_world`` returns it to the resumable bucket. Terminal and
cancelled runs never auto-retry.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.exc import IntegrityError

from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.application.tasks.service import ReconcileReport, TaskService
from worldsim.application.tracing.service import (
    ManifestSpec,
    ModelGatewayLike,
    TracedCall,
    TraceService,
)
from worldsim.application.transactions.canonical import (
    CanonicalTransaction,
    CommitRequest,
    CommitResult,
    MemorySpec,
    ObservationSpec,
    OutboxSpec,
    canonical_input_hash,
)
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.effects import AdvanceClockEffect
from worldsim.domain.enums import (
    STAGE0_ACTION_FAMILIES,
    ActionFamily,
    CommandType,
    EventType,
    PhaseRunState,
    TaskRunState,
    UserRole,
    Visibility,
)
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.perception import ObservationFact
from worldsim.domain.phases import PhaseRun, PhaseSnapshot, SnapshotCharacter
from worldsim.domain.rules.phases import require_next
from worldsim.domain.tasks import PHASE_ADVANCE_TASK, Lease, TaskRun
from worldsim.domain.time import FictionalTime, absolute_index, utcnow
from worldsim.domain.tracing import ManifestSource

TICK_PROMPT_VERSION = "stage0-tick-v1"
TICK_ROLE = "narrator"

#: Run states that refuse automatic advancement.
_BLOCKED_RUN_STATES = frozenset(
    {PhaseRunState.PAUSED, PhaseRunState.TERMINAL_FAILED, PhaseRunState.CANCELLED}
)

#: Input errors that poison the run terminally; everything else (notably
#: version conflicts) is retryable.
_TERMINAL_INPUT_CODES = frozenset(
    {
        ErrorCode.VALIDATION_FAILED,
        ErrorCode.PRECONDITION_FAILED,
        ErrorCode.UNSUPPORTED_ACTION,
        ErrorCode.NOT_FOUND,
        ErrorCode.IDEMPOTENCY_CONFLICT,
    }
)


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


def _derive(name: str, *parts: object) -> UUID:
    return uuid5(NAMESPACE_URL, f"worldsim:{name}:{':'.join(str(part) for part in parts)}")


def derive_run_id(world_id: UUID, absolute_index: int) -> UUID:
    return _derive("phase_run", world_id.hex, absolute_index)


def derive_snapshot_id(run_id: UUID) -> UUID:
    return _derive("snapshot", run_id.hex)


def task_key_for(absolute_index: int) -> str:
    return f"phase_advance:{absolute_index}"


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


@dataclass(frozen=True)
class AdvanceReport:
    command_id: UUID
    run_id: UUID
    world_id: UUID
    absolute_index: int
    event_id: UUID
    sequence: int
    snapshot_id: UUID
    content_hash: str
    call_id: UUID
    manifest_id: UUID
    task_id: UUID
    tasks_requeued: int
    outbox_requeued: int
    duplicate: bool


@dataclass(frozen=True)
class ReconcileWorldReport:
    tasks_requeued: int
    outbox_requeued: int
    open_run_id: UUID | None
    open_state: str | None


class PhaseOrchestrator:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        canonical: CanonicalTransaction,
        tasks: TaskService,
        traces: TraceService,
        gateway: ModelGatewayLike,
        *,
        lease_s: float = 60.0,
        fault_hook: Callable[[str], None] | None = None,
    ) -> None:
        self._factory = uow_factory
        self._canonical = canonical
        self._tasks = tasks
        self._traces = traces
        self._gateway = gateway
        self._lease_s = lease_s
        self._hook = fault_hook

    def _fire(self, point: str) -> None:
        if self._hook is not None:
            self._hook(point)

    async def advance_world(self, world_id: UUID, idempotency_key: str) -> AdvanceReport:
        if not idempotency_key or len(idempotency_key) > 128:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                "idempotency key must be 1..128 characters",
                {"length": len(idempotency_key)},
            )
        reconcile = await self._tasks.reconcile()
        replayed = await self._replay(world_id, idempotency_key, reconcile)
        if replayed is not None:
            return replayed
        while True:
            async with self._factory() as uow:
                world = await uow.worlds.get(world_id)
                open_run = await uow.phases.find_open_run(world_id)
            current = absolute_index(world.day, world.phase)
            target = current + 1
            if open_run is not None and open_run.absolute_index > target:
                raise DomainError(
                    ErrorCode.INVARIANT_VIOLATED,
                    f"clock behind open phase run {open_run.id}",
                    {"run_id": str(open_run.id), "target": target},
                )
            if open_run is not None and open_run.absolute_index < target:
                # The tick committed but post-work did not: seal and finalize
                # the stale run first, then advance the next index below.
                await self._complete_stale_run(world_id, open_run)
                continue
            following = require_next(FictionalTime(day=world.day, phase=world.phase), target)
            run_id = _derive("phase_run", world_id.hex, target)
            task_key = f"phase_advance:{target}"
            command_key = f"advance_phase:{idempotency_key}"
            command_id = _derive("command", world_id.hex, idempotency_key)
            snapshot_id = _derive("snapshot", run_id.hex)
            owner = f"orchestrator:{run_id.hex}"

            try:
                async with self._factory() as uow:
                    await uow.phases.create_run(
                        PhaseRun(id=run_id, world_id=world_id, absolute_index=target)
                    )
                    await uow.commit()
            except IntegrityError:
                pass
            self._fire("after_run_created")

            async with self._factory() as uow:
                run = await uow.phases.get_run(run_id)
            if run.absolute_index != target:
                raise DomainError(
                    ErrorCode.INVARIANT_VIOLATED,
                    f"phase run targets {run.absolute_index}, clock advanced to {target}",
                    {"run_id": str(run_id), "target": target},
                )
            if run.state == PhaseRunState.COMPLETED:
                raise DomainError(
                    ErrorCode.INVARIANT_VIOLATED,
                    f"phase run already completed for index {target} with clock behind it",
                    {"run_id": str(run_id), "target": target},
                )
            if run.state in _BLOCKED_RUN_STATES:
                raise DomainError(
                    ErrorCode.PRECONDITION_FAILED,
                    f"phase run is {run.state.value}; resume or reconcile before advancing",
                    {"run_id": str(run_id), "state": run.state.value},
                )

            task = await self._acquire_task(world_id, task_key, owner)
            try:
                traced, result = await self._commit_tick(
                    world_id=world_id,
                    run_id=run_id,
                    task=task,
                    current=current,
                    target=target,
                    following=following,
                    command_id=command_id,
                    command_key=command_key,
                )
                await self._set_state(run_id, PhaseRunState.WORLD_TICKED)
                self._fire("after_tick_committed")
                content_hash = await self._seal_snapshot(
                    world_id=world_id, run_id=run_id, snapshot_id=snapshot_id, target=target
                )
                await self._set_state(run_id, PhaseRunState.SNAPSHOT_SEALED)
                self._fire("after_snapshot_sealed")
                self._fire("before_finalize")
                await self._finalize(run_id, task.id, owner)
                return AdvanceReport(
                    command_id=command_id,
                    run_id=run_id,
                    world_id=world_id,
                    absolute_index=target,
                    event_id=result.event_id,
                    sequence=result.sequence,
                    snapshot_id=snapshot_id,
                    content_hash=content_hash,
                    call_id=traced.call_id,
                    manifest_id=traced.manifest_id,
                    task_id=task.id,
                    tasks_requeued=reconcile.tasks_requeued,
                    outbox_requeued=reconcile.outbox_requeued,
                    duplicate=result.duplicate,
                )
            except Exception as exc:
                await self._mark_failure(run_id, exc)
                raise

    async def _replay(
        self, world_id: UUID, idempotency_key: str, reconcile: ReconcileReport
    ) -> AdvanceReport | None:
        """Return the stored result when this key already committed a tick.

        Replay reflects the committed event; any post-work the original
        attempt did not reach heals on the next fresh-key advance.
        """
        async with self._factory() as uow:
            command_id = await uow.commands.get_by_key(world_id, f"advance_phase:{idempotency_key}")
            if command_id is None:
                return None
            event_id = await uow.commands.get_result(command_id)
            assert event_id is not None, "committed command must link its event"
            event = await uow.events.get_event(event_id)
            assert event.phase_run_id is not None, "detailed ticks always name a phase run"
            run = await uow.phases.get_run(event.phase_run_id)
            try:
                snapshot = await uow.phases.get_snapshot(_derive("snapshot", run.id.hex))
                content_hash = snapshot.content_hash
                snapshot_id = snapshot.id
            except DomainError:
                # Post-work never ran: report the hash sealing would store.
                # The clock cannot have moved past an unhealed run, so the
                # recomputed inputs still match the committed tick.
                pending = await self._snapshot_inputs(
                    world_id=world_id,
                    run_id=run.id,
                    snapshot_id=_derive("snapshot", run.id.hex),
                    target=run.absolute_index,
                )
                content_hash = pending.content_hash
                snapshot_id = pending.id
            calls = await uow.traces.list_for_phase_run(run.id)
            assert calls, "committed tick must have a traced call"
            manifest = await uow.traces.get_manifest(calls[-1].id)
            task = await uow.tasks.find_by_key(world_id, f"phase_advance:{run.absolute_index}")
            assert task is not None, "committed tick must own its task"
            return AdvanceReport(
                command_id=command_id,
                run_id=run.id,
                world_id=world_id,
                absolute_index=run.absolute_index,
                event_id=event_id,
                sequence=event.sequence,
                snapshot_id=snapshot_id,
                content_hash=content_hash,
                call_id=calls[-1].id,
                manifest_id=manifest.id,
                task_id=task.id,
                tasks_requeued=reconcile.tasks_requeued,
                outbox_requeued=reconcile.outbox_requeued,
                duplicate=True,
            )

    async def _complete_stale_run(self, world_id: UUID, run: PhaseRun) -> None:
        """Seal and finalize a run whose tick committed before a crash."""
        index = run.absolute_index
        snapshot_id = _derive("snapshot", run.id.hex)
        owner = f"orchestrator:{run.id.hex}"
        async with self._factory() as uow:
            world = await uow.worlds.get(world_id)
        if absolute_index(world.day, world.phase) != index:
            raise DomainError(
                ErrorCode.INVARIANT_VIOLATED,
                f"clock moved past unfinalized phase run {run.id}",
                {"run_id": str(run.id), "index": index},
            )
        task = await self._acquire_task(world_id, f"phase_advance:{index}", owner)
        try:
            async with self._factory() as uow:
                event = await uow.events.find_by_phase_run(world_id, run.id)
            if event is None:
                raise DomainError(
                    ErrorCode.INVARIANT_VIOLATED,
                    f"stale phase run has no committed tick: {run.id}",
                    {"run_id": str(run.id), "index": index},
                )
            await self._set_state(run.id, PhaseRunState.WORLD_TICKED)
            await self._seal_snapshot(
                world_id=world_id, run_id=run.id, snapshot_id=snapshot_id, target=index
            )
            await self._set_state(run.id, PhaseRunState.SNAPSHOT_SEALED)
            await self._finalize(run.id, task.id, owner)
        except Exception as exc:
            await self._mark_failure(run.id, exc)
            raise

    async def _mark_failure(self, run_id: UUID, exc: BaseException) -> None:
        # The task stays running under the deterministic owner: it is a
        # crash-recovery lock, not a job. The run row carries the failure
        # state; expiry lets any later advance reclaim the lease.
        if isinstance(exc, DomainError) and exc.code in _TERMINAL_INPUT_CODES:
            await self._set_state(run_id, PhaseRunState.TERMINAL_FAILED)
        else:
            await self._set_state(run_id, PhaseRunState.RETRYABLE_FAILED)

    async def _acquire_task(self, world_id: UUID, task_key: str, owner: str) -> TaskRun:
        task = await self._tasks.create_task(world_id, PHASE_ADVANCE_TASK, task_key)
        now = utcnow()
        lease = task.lease
        if (
            task.state == TaskRunState.RUNNING
            and lease is not None
            and lease.owner == owner
            and lease.expires_at > now
        ):
            if await self._tasks.heartbeat(task.id, owner, self._lease_s):
                return task
        attempt = lease.attempt + 1 if lease is not None else 1
        max_attempts = lease.max_attempts if lease is not None else 3
        claimed = await self._tasks.claim_task(
            task.id,
            owner,
            Lease(
                owner=owner,
                claimed_at=now,
                expires_at=now + timedelta(seconds=self._lease_s),
                attempt=attempt,
                max_attempts=max_attempts,
                input_version=1,
                idempotency_key=task_key,
            ),
        )
        if claimed is None:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                f"phase task held by another owner: {task_key}",
                {"task_id": str(task.id)},
            )
        return claimed

    async def _commit_tick(
        self,
        *,
        world_id: UUID,
        run_id: UUID,
        task: TaskRun,
        current: int,
        target: int,
        following: FictionalTime,
        command_id: UUID,
        command_key: str,
    ) -> tuple[TracedCall, CommitResult]:
        async with self._factory() as uow:
            world = await uow.worlds.get(world_id)
            characters = await uow.characters.list_for_world(world_id)
        if ActionFamily.WAIT not in STAGE0_ACTION_FAMILIES:
            raise DomainError(ErrorCode.UNSUPPORTED_ACTION, "stage 0 tick requires the wait family")
        prompt = (
            f"Advance {world.name} from day {world.day} {world.phase.value} "
            f"to day {following.day} {following.phase.value} with "
            f"{len(characters)} characters present. Continue their activities; "
            "narrate the transition."
        )
        traced = await self._traces.run_call(
            ManifestSpec(
                role=TICK_ROLE,
                profile=self._gateway.profile,
                prompt_version=TICK_PROMPT_VERSION,
                world_id=world_id,
                phase_run_id=run_id,
                task_run_id=task.id,
                sources=[
                    ManifestSource(
                        source_id=character.id.hex,
                        kind="character",
                        owner_id=character.id,
                        visibility=Visibility.PRIVATE,
                        reason="tick presence",
                    )
                    for character in characters
                ],
                budgets={"characters": len(characters)},
            ),
            self._gateway,
            CompletionRequest(prompt=prompt, max_tokens=256),
        )
        beat = traced.result.text
        result = await self._canonical.commit(
            CommitRequest(
                command_id=command_id,
                world_id=world_id,
                idempotency_key=command_key,
                actor_role=UserRole.SYSTEM.value,
                command_type=CommandType.ADVANCE_PHASE.value,
                expected_versions={str(world_id): world.version},
                payload={
                    "phase_run_id": run_id.hex,
                    "target_index": target,
                    "tick": "stage0",
                },
                input_hash=canonical_input_hash(
                    {
                        "world_id": world_id.hex,
                        "target": target,
                        "command": CommandType.ADVANCE_PHASE.value,
                        "seed": world.seed_version,
                    }
                ),
                absolute_index=target,
                phase_run_id=run_id,
                event_type=EventType.WORLD_TICKED,
                effects=[
                    AdvanceClockEffect(
                        affected_ids=[world_id],
                        expected_versions={str(world_id): world.version},
                        from_index=current,
                        to_index=target,
                    )
                ],
                observations=[
                    ObservationSpec(
                        observer_id=character.id,
                        facts=[
                            ObservationFact(
                                key="phase",
                                value=f"day {following.day} {following.phase.value}",
                            ),
                            ObservationFact(key="intent_family", value=ActionFamily.WAIT.value),
                            ObservationFact(key="beat", value=beat[:400]),
                        ],
                    )
                    for character in characters
                ],
                memories=[
                    MemorySpec(
                        owner_id=character.id,
                        text=beat[:1500],
                        visibility=Visibility.PRIVATE,
                        observation_index=index,
                    )
                    for index, character in enumerate(characters)
                ],
                outbox=[
                    OutboxSpec(
                        kind="phase_advanced",
                        payload={
                            "phase_run_id": run_id.hex,
                            "absolute_index": target,
                        },
                        key=f"phase_advanced:{world_id.hex}:{target}",
                    )
                ],
            )
        )
        return traced, result

    async def _snapshot_inputs(
        self, *, world_id: UUID, run_id: UUID, snapshot_id: UUID, target: int
    ) -> PhaseSnapshot:
        async with self._factory() as uow:
            world = await uow.worlds.get(world_id)
            characters = await uow.characters.list_for_world(world_id)
        members = sorted((character.id.hex, character.version) for character in characters)
        content_hash = _snapshot_hash(world_id, run_id, target, world.version, list(members))
        return PhaseSnapshot(
            id=snapshot_id,
            world_id=world_id,
            phase_run_id=run_id,
            absolute_index=target,
            world_version=world.version,
            characters=[
                SnapshotCharacter(character_id=character.id, version=character.version)
                for character in characters
            ],
            content_hash=content_hash,
        )

    async def _seal_snapshot(
        self, *, world_id: UUID, run_id: UUID, snapshot_id: UUID, target: int
    ) -> str:
        snapshot = await self._snapshot_inputs(
            world_id=world_id, run_id=run_id, snapshot_id=snapshot_id, target=target
        )
        content_hash = snapshot.content_hash
        try:
            async with self._factory() as uow:
                await uow.phases.add_snapshot(snapshot)
                await uow.commit()
        except IntegrityError as exc:
            async with self._factory() as uow:
                stored = await uow.phases.get_snapshot(snapshot_id)
            if stored.content_hash != content_hash:
                raise DomainError(
                    ErrorCode.INVARIANT_VIOLATED,
                    "sealed snapshot disagrees with the recomputed tick",
                    {"snapshot_id": str(snapshot_id)},
                ) from exc
        return content_hash

    async def _set_state(self, run_id: UUID, state: PhaseRunState) -> None:
        async with self._factory() as uow:
            await uow.phases.set_run_state(run_id, state.value)
            await uow.commit()

    async def _finalize(self, run_id: UUID, task_id: UUID, owner: str) -> None:
        async with self._factory() as uow:
            await uow.phases.set_run_state(run_id, PhaseRunState.COMPLETED.value)
            if not await uow.tasks.finish(task_id, owner, "succeeded"):
                raise DomainError(
                    ErrorCode.PRECONDITION_FAILED,
                    "phase task left the running state before finalize",
                    {"task_id": str(task_id)},
                )
            await uow.commit()

    async def pause_world(self, world_id: UUID) -> PhaseRun:
        async with self._factory() as uow:
            run = await uow.phases.find_open_run(world_id)
        if run is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"no open phase run for world {world_id}")
        if run.state != PhaseRunState.CREATED:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "stage 0 pauses pre-commit runs only; resume or reconcile instead",
                {"run_id": str(run.id), "state": run.state.value},
            )
        # The task lease stays with the deterministic owner: pausing gates
        # the run state, and resume re-enters through the same lease.
        await self._set_state(run.id, PhaseRunState.PAUSED)
        async with self._factory() as uow:
            return await uow.phases.get_run(run.id)

    async def resume_world(self, run_id: UUID) -> PhaseRun:
        async with self._factory() as uow:
            run = await uow.phases.get_run(run_id)
        if run.state != PhaseRunState.PAUSED:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "only a paused run resumes",
                {"run_id": str(run_id), "state": run.state.value},
            )
        await self._set_state(run_id, PhaseRunState.RETRYABLE_FAILED)
        async with self._factory() as uow:
            return await uow.phases.get_run(run_id)

    async def reconcile_world(self, world_id: UUID) -> ReconcileWorldReport:
        reconcile = await self._tasks.reconcile()
        async with self._factory() as uow:
            run = await uow.phases.find_open_run(world_id)
        return ReconcileWorldReport(
            tasks_requeued=reconcile.tasks_requeued,
            outbox_requeued=reconcile.outbox_requeued,
            open_run_id=run.id if run is not None else None,
            open_state=run.state.value if run is not None else None,
        )
