"""S0-ORCH-001: deterministic advance, resume, pause, reconcile (owned by S0-ORCH-001)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from worldsim.application.commands.seed_world import SeedService
from worldsim.application.orchestration.service import PhaseOrchestrator
from worldsim.application.ports.model_gateway import ModelUnavailableError
from worldsim.application.tasks.service import TaskService
from worldsim.application.tracing.service import TraceService
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.domain.enums import EventType, PhaseName, PhaseRunState
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.models.events import WorldEventRow
from worldsim.infrastructure.models.phases import PhaseSnapshotRow
from worldsim.infrastructure.repositories.unit_of_work import (
    SqlAlchemyUnitOfWork,
    create_unit_of_work,
)
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.tracing.langsmith import NullExporter

SEED_DIR = Path(__file__).parent.parent.parent / "content" / "seeds" / "stage0"
BEAT = "Dawn breaks over the Hearth, and the market stirs."
KEY = "stage0-test-advance-1"
KEY2 = "stage0-test-advance-2"


def _factory_for(engine: AsyncEngine) -> Callable[[], SqlAlchemyUnitOfWork]:
    def _factory() -> SqlAlchemyUnitOfWork:
        return create_unit_of_work(engine)

    return _factory


def _orchestrator(
    engine: AsyncEngine,
    gateway: FakeGateway,
    hook: Callable[[str], None] | None = None,
) -> PhaseOrchestrator:
    factory = _factory_for(engine)
    return PhaseOrchestrator(
        factory,
        CanonicalTransaction(factory),
        TaskService(factory),
        TraceService(factory, NullExporter()),
        gateway,
        lease_s=60.0,
        fault_hook=hook,
    )


def _gateway_with(*beats: str) -> FakeGateway:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    for beat in beats:
        gateway.enqueue_text(beat, 10, 5)
    return gateway


class _Once:
    """One-shot crash at a hook point; later passes disarm it."""

    def __init__(self, point: str) -> None:
        self._point = point
        self.fired = False

    def __call__(self, point: str) -> None:
        if point == self._point and not self.fired:
            self.fired = True
            raise RuntimeError(f"crash at {point}")


async def _seeded_world(engine: AsyncEngine) -> UUID:
    return (await SeedService(_factory_for(engine), SEED_DIR).import_seed()).world_id


async def _event_count(engine: AsyncEngine, world_id: UUID) -> int:
    async with AsyncSession(engine) as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(WorldEventRow)
                .where(WorldEventRow.world_id == world_id)
            )
        ).scalar_one()


async def _snapshot_count(engine: AsyncEngine, world_id: UUID) -> int:
    async with AsyncSession(engine) as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(PhaseSnapshotRow)
                .where(PhaseSnapshotRow.world_id == world_id)
            )
        ).scalar_one()


async def _world_state(engine: AsyncEngine, world_id: UUID):  # type: ignore[no-untyped-def]
    async with create_unit_of_work(engine) as uow:
        world = await uow.worlds.get(world_id)
        run = await uow.phases.find_open_run(world_id)
        task = await uow.tasks.find_by_key(world_id, "phase_advance:1")
        events = await uow.events.count_events(world_id)
        return world, run, task, events


def test_advance_commits_deterministic_tick(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            world_id = await _seeded_world(engine)
            report = await _orchestrator(engine, _gateway_with(BEAT)).advance_world(world_id, KEY)
            assert report.absolute_index == 1
            assert report.sequence == 2
            assert not report.duplicate
            async with create_unit_of_work(engine) as uow:
                world = await uow.worlds.get(world_id)
                assert (world.day, world.phase) == (1, PhaseName.SUNRISE)
                assert world.version == 1
                run = await uow.phases.get_run(report.run_id)
                assert run.state == PhaseRunState.COMPLETED
                assert await uow.phases.find_open_run(world_id) is None
                snapshot = await uow.phases.get_snapshot(report.snapshot_id)
                assert snapshot.phase_run_id == report.run_id
                assert snapshot.world_version == 1
                assert snapshot.content_hash == report.content_hash
                assert sorted(c.version for c in snapshot.characters) == [0, 0]
                event = await uow.events.get_event(report.event_id)
                assert event.event_type == EventType.WORLD_TICKED
                assert event.absolute_index == 1
                assert event.phase_run_id == report.run_id
                assert len(await uow.events.list_effects(report.event_id)) == 1
                assert await uow.events.count_events(world_id) == 2
                observations = await uow.perception.observations_for_event(report.event_id)
                assert len(observations) == 2
                assert all(
                    "day 1 sunrise" in f.value
                    for o in observations
                    for f in o.facts
                    if f.key == "phase"
                )
                memory_total = 0
                for observer in observations:
                    owned = await uow.perception.memories_for_owner(observer.observer_character_id)
                    # Wren also holds the seed secret; only the tick memory links here.
                    memory_total += sum(1 for memory in owned if memory.event_id == report.event_id)
                assert memory_total == 2
                outbox = await uow.outbox.count_pending(world_id)
                assert outbox == 1
                task = await uow.tasks.find_by_key(world_id, "phase_advance:1")
                assert task is not None and task.state.value == "succeeded"
                call = await uow.traces.get_call(report.call_id)
                assert call.phase_run_id == report.run_id
                assert call.task_run_id == report.task_id
                manifest = await uow.traces.get_manifest(report.call_id)
                assert manifest.id == report.manifest_id
                assert manifest.role == "narrator"
                assert len(manifest.sources) == 2
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_resume_after_run_created(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            world_id = await _seeded_world(engine)
            hook = _Once("after_run_created")
            with pytest.raises(RuntimeError, match="crash at after_run_created"):
                await _orchestrator(engine, _gateway_with(BEAT), hook).advance_world(world_id, KEY)
            report = await _orchestrator(engine, _gateway_with(BEAT)).advance_world(world_id, KEY)
            assert not report.duplicate
            assert report.sequence == 2
            world, run, _task, events = await _world_state(engine, world_id)
            assert (world.day, world.phase) == (1, PhaseName.SUNRISE)
            assert run is None
            assert events == 2
            assert await _event_count(engine, world_id) == 2
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_same_key_replays_without_new_rows(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            world_id = await _seeded_world(engine)
            hook = _Once("after_tick_committed")
            with pytest.raises(RuntimeError, match="crash at after_tick_committed"):
                await _orchestrator(engine, _gateway_with("First beat."), hook).advance_world(
                    world_id, KEY
                )
            # Same key after the crash: the committed tick replays verbatim.
            replay = await _orchestrator(engine, _gateway_with("Second beat.")).advance_world(
                world_id, KEY
            )
            assert replay.duplicate
            assert replay.sequence == 2
            assert await _event_count(engine, world_id) == 2
            assert await _snapshot_count(engine, world_id) == 0
            async with create_unit_of_work(engine) as uow:
                run = await uow.phases.get_run(replay.run_id)
                assert run.state == PhaseRunState.RETRYABLE_FAILED
            report = await _orchestrator(engine, _gateway_with("Third beat.")).advance_world(
                world_id, KEY2
            )
            assert not report.duplicate
            assert report.absolute_index == 2
            assert report.sequence == 3
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(world_id) == 3
                world = await uow.worlds.get(world_id)
                assert (world.day, world.phase) == (1, PhaseName.MORNING)
                assert world.version == 2
                assert await uow.outbox.count_pending(world_id) == 2
                assert (await uow.phases.get_run(replay.run_id)).state == PhaseRunState.COMPLETED
                assert (await uow.phases.get_run(report.run_id)).state == PhaseRunState.COMPLETED
            assert await _snapshot_count(engine, world_id) == 2
            assert await _event_count(engine, world_id) == 3
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_resume_before_finalize_reuses_snapshot(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            world_id = await _seeded_world(engine)
            hook = _Once("before_finalize")
            with pytest.raises(RuntimeError, match="crash at before_finalize"):
                await _orchestrator(engine, _gateway_with(BEAT), hook).advance_world(world_id, KEY)
            # Same key replays tick 1; the sealed snapshot stays single.
            replay = await _orchestrator(engine, _gateway_with(BEAT)).advance_world(world_id, KEY)
            assert replay.duplicate
            assert replay.sequence == 2
            assert await _snapshot_count(engine, world_id) == 1
            assert await _event_count(engine, world_id) == 2
            # Fresh key heals (snapshot hash must match), then ticks index 2.
            report = await _orchestrator(engine, _gateway_with(BEAT)).advance_world(world_id, KEY2)
            assert not report.duplicate
            assert report.sequence == 3
            async with create_unit_of_work(engine) as uow:
                snapshot = await uow.phases.get_snapshot(report.snapshot_id)
                assert snapshot.content_hash == report.content_hash
                assert snapshot.absolute_index == 2
                run = await uow.phases.get_run(report.run_id)
                assert run.state == PhaseRunState.COMPLETED
            assert await _snapshot_count(engine, world_id) == 2
            assert await _event_count(engine, world_id) == 3
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_pause_blocks_until_resume(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            world_id = await _seeded_world(engine)
            hook = _Once("after_run_created")
            with pytest.raises(RuntimeError, match="crash at after_run_created"):
                await _orchestrator(engine, _gateway_with(BEAT), hook).advance_world(world_id, KEY)
            orch = _orchestrator(engine, _gateway_with(BEAT))
            paused = await orch.pause_world(world_id)
            assert paused.state == PhaseRunState.PAUSED
            with pytest.raises(DomainError) as excinfo:
                await orch.advance_world(world_id, KEY)
            assert excinfo.value.code is ErrorCode.PRECONDITION_FAILED
            with pytest.raises(DomainError) as excinfo:
                await orch.pause_world(world_id)
            assert excinfo.value.code is ErrorCode.PRECONDITION_FAILED
            resumed = await orch.resume_world(paused.id)
            assert resumed.state == PhaseRunState.RETRYABLE_FAILED
            with pytest.raises(DomainError) as excinfo:
                await orch.resume_world(paused.id)
            assert excinfo.value.code is ErrorCode.PRECONDITION_FAILED
            report = await orch.advance_world(world_id, KEY)
            assert not report.duplicate
            _world, run, _task, events = await _world_state(engine, world_id)
            assert run is None
            assert events == 2
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_terminal_run_blocks_advance(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            world_id = await _seeded_world(engine)
            hook = _Once("after_run_created")
            with pytest.raises(RuntimeError, match="crash at after_run_created"):
                await _orchestrator(engine, _gateway_with(BEAT), hook).advance_world(world_id, KEY)
            async with create_unit_of_work(engine) as uow:
                run = await uow.phases.find_open_run(world_id)
                assert run is not None
                await uow.phases.set_run_state(run.id, PhaseRunState.TERMINAL_FAILED.value)
                await uow.commit()
            with pytest.raises(DomainError) as excinfo:
                await _orchestrator(engine, _gateway_with(BEAT)).advance_world(world_id, KEY)
            assert excinfo.value.code is ErrorCode.PRECONDITION_FAILED
            _world, _run, _task, events = await _world_state(engine, world_id)
            assert events == 1
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_gateway_failure_marks_retryable_without_commit(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            world_id = await _seeded_world(engine)
            gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
            gateway.enqueue_error(ModelUnavailableError("provider down"))
            with pytest.raises(ModelUnavailableError):
                await _orchestrator(engine, gateway).advance_world(world_id, KEY)
            async with create_unit_of_work(engine) as uow:
                run = await uow.phases.find_open_run(world_id)
                assert run is not None
                assert run.state == PhaseRunState.RETRYABLE_FAILED
                assert await uow.events.count_events(world_id) == 1
            report = await _orchestrator(engine, _gateway_with(BEAT)).advance_world(world_id, KEY)
            assert not report.duplicate
            assert report.sequence == 2
            _world, run, task, events = await _world_state(engine, world_id)
            assert run is None
            assert task is not None and task.state.value == "succeeded"
            assert events == 2
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_reconcile_reports_open_run(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            world_id = await _seeded_world(engine)
            orch = _orchestrator(engine, _gateway_with(BEAT))
            clean = await orch.reconcile_world(world_id)
            assert (clean.open_run_id, clean.open_state) == (None, None)
            hook = _Once("after_run_created")
            with pytest.raises(RuntimeError, match="crash at after_run_created"):
                await _orchestrator(engine, _gateway_with(BEAT), hook).advance_world(world_id, KEY)
            stale = await orch.reconcile_world(world_id)
            assert stale.open_state == PhaseRunState.CREATED.value
            assert stale.open_run_id is not None
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_pause_without_open_run_fails(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            world_id = await _seeded_world(engine)
            with pytest.raises(DomainError) as excinfo:
                await _orchestrator(engine, _gateway_with(BEAT)).pause_world(world_id)
            assert excinfo.value.code is ErrorCode.NOT_FOUND
        finally:
            await engine.dispose()

    asyncio.run(_inner())
