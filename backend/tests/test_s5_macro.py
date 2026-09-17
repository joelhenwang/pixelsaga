"""Stage 5 macro engine tests: clock, schedules, replay, interruption, guards."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest

from worldsim.application.macro.engine import MacroEngine
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.domain.enums import EventType, MacroResolution, MacroRunState
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


def test_week_advance_moves_clock_and_replays(migrated_db: None) -> None:
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

            first = await macro.advance_period(wid, 1, MacroResolution.WEEK)
            assert first.run.state == MacroRunState.COMPLETED
            assert first.duplicate is False

            async with factory() as uow:
                world = await uow.worlds.get(wid)
                assert absolute_index(world.day, world.phase) == 70
                events = await uow.events.list_range(wid, 0, 20)
            ticks = [e for e in events if e.event_type == EventType.MACRO_TICKED]
            assert len(ticks) == 1
            assert ticks[0].absolute_index == 69
            assert ticks[0].phase_run_id is None

            second = await macro.advance_period(wid, 1, MacroResolution.WEEK)
            assert second.duplicate is True
            assert second.event_ids == first.event_ids
            async with factory() as uow:
                again = await uow.events.list_range(wid, 0, 20)
            assert len([e for e in again if e.event_type == EventType.MACRO_TICKED]) == 1
        finally:
            await engine.dispose()

    _run(_inner())


def test_schedules_fire_only_inside_window(migrated_db: None) -> None:
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
                    ScheduledEffect(id=new_schedule_id(), world_id=wid, due_absolute=5, kind="note")
                )
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(), world_id=wid, due_absolute=75, kind="note"
                    )
                )
                await uow.commit()

            result = await macro.advance_period(wid, 1, MacroResolution.WEEK)
            assert result.run.state == MacroRunState.COMPLETED

            async with factory() as uow:
                due = await uow.schedules.list_due(wid, 100)
                events = await uow.events.list_range(wid, 0, 20)
                effects = await uow.macro.list_effects(result.run.id)
            assert [s.due_absolute for s in due] == [75]
            fired = [e for e in events if e.event_type == EventType.SCHEDULE_FIRED]
            assert len(fired) == 1 and fired[0].absolute_index == 5
            assert sorted(e.kind.value for e in effects) == ["clock_advance", "schedule_progress"]
        finally:
            await engine.dispose()

    _run(_inner())


def test_interruption_writes_no_state(migrated_db: None) -> None:
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

            async def _break(world_id: UUID, start: int, end: int) -> int | None:
                assert (world_id, start, end) == (wid, 0, 70)
                return 3

            result = await macro.advance_period(wid, 1, MacroResolution.WEEK, salience_break=_break)
            assert result.run.state == MacroRunState.INTERRUPTED
            assert result.event_ids == []

            async with factory() as uow:
                world = await uow.worlds.get(wid)
                assert absolute_index(world.day, world.phase) == 0
                records = await uow.macro.list_interruptions(result.run.id)
            assert len(records) == 1 and records[0].at_absolute == 3

            with pytest.raises(DomainError) as exc_info:
                await macro.advance_period(wid, 1, MacroResolution.WEEK)
            assert exc_info.value.code == ErrorCode.PRECONDITION_FAILED
        finally:
            await engine.dispose()

    _run(_inner())


def test_non_consecutive_clock_rejected(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            macro = MacroEngine(factory, CanonicalTransaction(factory))
            async with factory() as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test", day=2))
                await uow.versions.ensure(wid, wid, "world")
                await uow.commit()

            with pytest.raises(DomainError) as exc_info:
                await macro.advance_period(wid, 1, MacroResolution.WEEK)
            assert exc_info.value.code == ErrorCode.PRECONDITION_FAILED

            async with factory() as uow:
                world = await uow.worlds.get(wid)
                assert absolute_index(world.day, world.phase) == 10
        finally:
            await engine.dispose()

    _run(_inner())


def test_crash_resume_links_without_duplicating(migrated_db: None) -> None:
    """A run stuck RUNNING after its commits resumes into the same rows."""

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
                    ScheduledEffect(id=new_schedule_id(), world_id=wid, due_absolute=5, kind="note")
                )
                await uow.commit()

            first = await macro.advance_period(wid, 1, MacroResolution.WEEK)
            assert first.run.state == MacroRunState.COMPLETED

            async with factory() as uow:
                corner = await uow.macro.get_run(first.run.id)
                await uow.macro.save_run(
                    corner.model_copy(update={"state": MacroRunState.RUNNING}), corner.version
                )
                await uow.commit()

            resumed = await macro.advance_period(wid, 1, MacroResolution.WEEK)
            assert resumed.run.state == MacroRunState.COMPLETED
            assert resumed.duplicate is False
            async with factory() as uow:
                effects = await uow.macro.list_effects(first.run.id)
                assert sorted(e.kind.value for e in effects) == [
                    "clock_advance",
                    "schedule_progress",
                ]
                assert len({e.event_id for e in effects}) == 2
                events = await uow.events.list_range(wid, 0, 20)
            assert len([e for e in events if e.event_type == EventType.MACRO_TICKED]) == 1
            assert len([e for e in events if e.event_type == EventType.SCHEDULE_FIRED]) == 1
        finally:
            await engine.dispose()

    _run(_inner())


def test_overdue_schedule_fires_late_with_marker(migrated_db: None) -> None:
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

            first = await macro.advance_period(wid, 1, MacroResolution.DAY)
            assert first.run.state == MacroRunState.COMPLETED

            async with factory() as uow:
                await uow.schedules.add(
                    ScheduledEffect(id=new_schedule_id(), world_id=wid, due_absolute=5, kind="note")
                )
                await uow.commit()

            second = await macro.advance_period(wid, 2, MacroResolution.DAY)
            assert second.run.state == MacroRunState.COMPLETED
            async with factory() as uow:
                events = await uow.events.list_range(wid, 0, 20)
            fired = [e for e in events if e.event_type == EventType.SCHEDULE_FIRED]
            assert len(fired) == 1
            assert fired[0].absolute_index == 5
            assert fired[0].summary.get("late") == "true"
        finally:
            await engine.dispose()

    _run(_inner())
