"""Activity and travel-route persistence (owned by S2-CONTRACT-001)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from worldsim.domain.activities import Activity, TravelRoute, focus_for_seat
from worldsim.domain.enums import ActivityKind, ActivityStatus, FocusSlot
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    new_activity_id,
    new_character_id,
    new_location_id,
    new_route_id,
    new_world_id,
)
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


def _run(awaitable: Any) -> None:
    asyncio.run(awaitable)


def test_activity_lifecycle_guards(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                wid = new_world_id()
                cid = new_character_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s2-test"))
                await uow.characters.add_identity(cid, wid, "Wren")
                await uow.commit()
            async with create_unit_of_work(engine) as uow:
                activity = Activity(
                    id=new_activity_id(),
                    world_id=wid,
                    character_id=cid,
                    kind=ActivityKind.TRAVEL,
                    start_absolute=3,
                    duration_phases=2,
                    payload={"to": "market"},
                )
                assert activity.status == ActivityStatus.PLANNED
                await uow.activities.add(activity)
                await uow.commit()
            async with create_unit_of_work(engine) as uow:
                assert await uow.activities.list_active_for_world(wid) == []
                live = activity.model_copy(update={"status": ActivityStatus.ACTIVE})
                saved = await uow.activities.save(live, 0)
                assert saved.version == 1
                assert saved.status == ActivityStatus.ACTIVE
                progressed = saved.model_copy(update={"progress_phases": 2})
                saved_again = await uow.activities.save(progressed, 1)
                assert saved_again.progress_phases == 2
                with pytest.raises(DomainError) as exc_info:
                    await uow.activities.save(progressed, 1)
                assert exc_info.value.code == ErrorCode.VERSION_CONFLICT
        finally:
            await engine.dispose()

    _run(_inner())


def test_route_legs_unique_per_world(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                wid = new_world_id()
                home = new_location_id()
                market = new_location_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s2-test"))
                await uow.locations.add(
                    Location(id=home, world_id=wid, name="Hearth", region="Vale", capacity=4)
                )
                await uow.locations.add(
                    Location(id=market, world_id=wid, name="Market", region="Vale", capacity=9)
                )
                await uow.commit()
            async with create_unit_of_work(engine) as uow:
                leg = TravelRoute(
                    id=new_route_id(),
                    world_id=wid,
                    from_location_id=home,
                    to_location_id=market,
                    duration_phases=2,
                    stamina_cost=3,
                )
                await uow.routes.add(leg)
                await uow.commit()
            async with create_unit_of_work(engine) as uow:
                legs = await uow.routes.list_for_world(wid)
                assert [(r.duration_phases, r.stamina_cost) for r in legs] == [(2, 3)]
                twin = TravelRoute(
                    id=new_route_id(),
                    world_id=wid,
                    from_location_id=home,
                    to_location_id=market,
                    duration_phases=2,
                    stamina_cost=3,
                )
                with pytest.raises(IntegrityError):
                    await uow.routes.add(twin)
        finally:
            await engine.dispose()

    _run(_inner())


def test_focus_seats_two_mains_two_subs() -> None:
    assert [focus_for_seat(i) for i in range(6)] == [
        FocusSlot.MAIN,
        FocusSlot.MAIN,
        FocusSlot.SUB,
        FocusSlot.SUB,
        FocusSlot.COMPANION,
        FocusSlot.COMPANION,
    ]
