"""Stage 2 time slice: day rollover, previous-complete guard, quiet phases, schedules."""

from __future__ import annotations

from typing import Any

import pytest

from worldsim.domain.enums import ActionFamily, PhaseName
from worldsim.domain.ids import new_schedule_id, new_world_id
from worldsim.domain.rules.phases import is_quiet_phase, next_time, require_next
from worldsim.domain.schedules import ScheduledEffect
from worldsim.domain.time import (
    PHASE_ORDER,
    FictionalTime,
    absolute_index,
    split_absolute,
)
from worldsim.domain.world import World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


def test_absolute_round_trips_a_month() -> None:
    for day in range(1, 31):
        for phase in PHASE_ORDER:
            index = absolute_index(day, phase)
            assert split_absolute(index) == (day, phase)


def test_next_time_walks_midnight_rollover() -> None:
    moment = FictionalTime(day=2, phase=PhaseName.MIDNIGHT)
    rolled = next_time(moment)
    assert (rolled.day, rolled.phase) == (3, PhaseName.DAWN)
    assert rolled.absolute == moment.absolute + 1


def test_require_next_rejects_skips_and_repeats() -> None:
    from worldsim.domain.errors import DomainError

    moment = FictionalTime(day=1, phase=PhaseName.MORNING)
    with pytest.raises(DomainError):
        require_next(moment, moment.absolute)
    with pytest.raises(DomainError):
        require_next(moment, moment.absolute + 2)
    assert require_next(moment, moment.absolute + 1).absolute == moment.absolute + 1


def test_quiet_means_empty_or_all_wait() -> None:
    assert is_quiet_phase([]) is True
    assert is_quiet_phase([ActionFamily.WAIT, ActionFamily.WAIT]) is True
    assert is_quiet_phase([ActionFamily.WAIT, ActionFamily.OBSERVE]) is False


def _bare_orchestrator() -> Any:
    """Orchestrator with real factory; only factory-touching methods are used."""
    from worldsim.application.orchestration.stage1 import Stage1Orchestrator
    from worldsim.application.tasks.service import TaskService
    from worldsim.application.tracing.service import TraceService
    from worldsim.application.transactions.canonical import CanonicalTransaction
    from worldsim.infrastructure.tracing.langsmith import NullExporter

    engine = create_engine(Settings())
    factory = lambda: create_unit_of_work(engine)  # noqa: E731
    return Stage1Orchestrator(
        factory,
        CanonicalTransaction(factory),
        TaskService(factory),
        TraceService(factory, NullExporter()),
        lambda role: (_ for _ in ()).throw(AssertionError(f"no gateway in time tests: {role}")),
        {},
    )


def test_previous_complete_guard(migrated_db: None) -> None:
    import asyncio

    from worldsim.domain.errors import DomainError

    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s2-test"))
                await uow.commit()
            orchestrator = _bare_orchestrator()
            await orchestrator._require_previous_complete(wid, 1)
            with pytest.raises(DomainError, match="previous phase 2"):
                await orchestrator._require_previous_complete(wid, 3)
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_schedules_fire_once_at_tick(migrated_db: None) -> None:
    import asyncio

    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                from worldsim.application.orchestration.service import derive_run_id
                from worldsim.domain.phases import PhaseRun

                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s2-test"))
                await uow.phases.create_run(
                    PhaseRun(id=derive_run_id(wid, 2), world_id=wid, absolute_index=2)
                )
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(),
                        world_id=wid,
                        due_absolute=2,
                        kind="note",
                        payload={"text": "market opens"},
                    )
                )
                await uow.commit()
            orchestrator = _bare_orchestrator()
            assert await orchestrator._fire_due_schedules(wid, 1) == 0
            assert await orchestrator._fire_due_schedules(wid, 2) == 1
            assert await orchestrator._fire_due_schedules(wid, 2) == 0
            async with create_unit_of_work(engine) as uow:
                assert await uow.schedules.list_due(wid, 9) == []
                events = await uow.events.list_range(wid, 0, 10)
                fired = [e for e in events if e.event_type == "schedule_fired"]
                assert len(fired) == 1
                assert fired[0].absolute_index == 2
        finally:
            await engine.dispose()

    asyncio.run(_inner())
