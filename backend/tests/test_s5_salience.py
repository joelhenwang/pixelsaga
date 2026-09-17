"""Stage 5 salience tests: selection, breaks, policy, detailed resume."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest

from worldsim.application.macro.engine import MacroEngine
from worldsim.application.macro.salience import find_break, macro_covers, select_resolution
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.domain.enums import MacroResolution, MacroRunState, ScheduleStatus
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_schedule_id, new_world_id
from worldsim.domain.schedules import ScheduledEffect
from worldsim.domain.time import absolute_index
from worldsim.domain.world import World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def _bare_stage1() -> Any:
    from worldsim.application.orchestration.stage1 import Stage1Orchestrator
    from worldsim.application.tasks.service import TaskService
    from worldsim.application.tracing.service import TraceService
    from worldsim.infrastructure.tracing.langsmith import NullExporter

    engine = create_engine(Settings())
    factory = lambda: create_unit_of_work(engine)  # noqa: E731
    return Stage1Orchestrator(
        factory,
        CanonicalTransaction(factory),
        TaskService(factory),
        TraceService(factory, NullExporter()),
        lambda role: (_ for _ in ()).throw(AssertionError(f"no gateway in salience tests: {role}")),
        {},
    )


def test_quiet_world_selects_year(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            async with factory() as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.commit()
            assert await select_resolution(factory, wid, 1) == MacroResolution.YEAR
        finally:
            await engine.dispose()

    _run(_inner())


def test_seeded_major_event_narrows_to_day_and_breaks(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            async with factory() as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.versions.ensure(wid, wid, "world")
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(),
                        world_id=wid,
                        due_absolute=25,
                        kind="invasion",
                        payload={"salient": True},
                    )
                )
                await uow.commit()

            assert await select_resolution(factory, wid, 1) == MacroResolution.DAY
            assert await find_break(factory, wid, 0, 70) == 25
            assert await find_break(factory, wid, 26, 70) is None

            macro = MacroEngine(factory, CanonicalTransaction(factory))

            async def _hook(world_id: UUID, start: int, end: int) -> int | None:
                return await find_break(factory, world_id, start, end)

            result = await macro.advance_period(wid, 1, MacroResolution.WEEK, salience_break=_hook)
            assert result.run.state == MacroRunState.INTERRUPTED
            async with factory() as uow:
                records = await uow.macro.list_interruptions(result.run.id)
            assert [r.at_absolute for r in records] == [25]
        finally:
            await engine.dispose()

    _run(_inner())


def test_pending_cap_forces_detailed(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            async with factory() as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.schedules.add(
                    ScheduledEffect(id=new_schedule_id(), world_id=wid, due_absolute=3, kind="note")
                )
                await uow.schedules.add(
                    ScheduledEffect(id=new_schedule_id(), world_id=wid, due_absolute=4, kind="note")
                )
                await uow.worlds.put_config(wid, "macro.max_pending_schedules", 1)
                await uow.commit()
            assert await select_resolution(factory, wid, 1) is None
        finally:
            await engine.dispose()

    _run(_inner())


def test_invalid_policy_rejected(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            async with factory() as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.worlds.put_config(wid, "macro.max_pending_schedules", "many")
                await uow.commit()
            with pytest.raises(DomainError) as exc_info:
                await select_resolution(factory, wid, 1)
            assert exc_info.value.code == ErrorCode.VALIDATION_FAILED
        finally:
            await engine.dispose()

    _run(_inner())


def test_detailed_resumes_at_macro_clock(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            macro = MacroEngine(factory, CanonicalTransaction(factory))
            async with factory() as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.versions.ensure(wid, wid, "world")
                await uow.commit()

            result = await macro.advance_period(wid, 1, MacroResolution.WEEK)
            assert result.run.state == MacroRunState.COMPLETED
            assert await macro_covers(factory, wid, 70) is True
            assert await macro_covers(factory, wid, 71) is False

            stage1 = _bare_stage1()
            await stage1._require_previous_complete(wid, 70)
            with pytest.raises(DomainError, match="previous phase 70"):
                await stage1._require_previous_complete(wid, 71)
        finally:
            await engine.dispose()

    _run(_inner())


def test_cancelled_break_unblocks_the_same_period(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            macro = MacroEngine(factory, CanonicalTransaction(factory))
            async with factory() as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.versions.ensure(wid, wid, "world")
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(),
                        world_id=wid,
                        due_absolute=25,
                        kind="invasion",
                        payload={"salient": True},
                    )
                )
                await uow.commit()

            async def _hook(world_id: UUID, start: int, end: int) -> int | None:
                return await find_break(factory, world_id, start, end)

            blocked = await macro.advance_period(wid, 1, MacroResolution.WEEK, salience_break=_hook)
            assert blocked.run.state == MacroRunState.INTERRUPTED

            async with factory() as uow:
                pending = await uow.schedules.list_due(wid, 69)
                assert len(pending) == 1
                await uow.schedules.save(
                    pending[0].model_copy(update={"status": ScheduleStatus.CANCELLED}),
                    pending[0].version,
                )
                await uow.commit()

            cleared = await macro.advance_period(wid, 1, MacroResolution.WEEK, salience_break=_hook)
            assert cleared.run.state == MacroRunState.COMPLETED
            assert cleared.run.id == blocked.run.id
            async with factory() as uow:
                world = await uow.worlds.get(wid)
                assert absolute_index(world.day, world.phase) == 70
                records = await uow.macro.list_interruptions(blocked.run.id)
                assert len(records) == 1
        finally:
            await engine.dispose()

    _run(_inner())


def test_still_blocked_retry_replays_without_new_rows(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            macro = MacroEngine(factory, CanonicalTransaction(factory))
            async with factory() as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.versions.ensure(wid, wid, "world")
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(),
                        world_id=wid,
                        due_absolute=25,
                        kind="invasion",
                        payload={"salient": True},
                    )
                )
                await uow.commit()

            async def _hook(world_id: UUID, start: int, end: int) -> int | None:
                return await find_break(factory, world_id, start, end)

            blocked = await macro.advance_period(wid, 1, MacroResolution.WEEK, salience_break=_hook)
            again = await macro.advance_period(wid, 1, MacroResolution.WEEK, salience_break=_hook)
            assert again.run.state == MacroRunState.INTERRUPTED
            assert again.duplicate is True
            async with factory() as uow:
                world = await uow.worlds.get(wid)
                assert absolute_index(world.day, world.phase) == 0
                records = await uow.macro.list_interruptions(blocked.run.id)
                assert len(records) == 1
        finally:
            await engine.dispose()

    _run(_inner())
