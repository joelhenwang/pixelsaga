"""Stage 2 activity mechanics: start guards, tick completion, idempotent control."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.application.commands.activities import (
    cancel_activity,
    interrupt_activity,
    resume_activity,
    start_activity,
)
from worldsim.domain.activities import effective_progress
from worldsim.domain.characters import Character
from worldsim.domain.enums import ActivityKind, ActivityStatus
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    new_character_id,
    new_location_id,
    new_phase_run_id,
    new_route_id,
    new_world_id,
)
from worldsim.domain.phases import PhaseRun
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


async def _seed_world(stamina: int = 80, mana: int = 40) -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            from worldsim.domain.activities import TravelRoute

            wid = new_world_id()
            home = new_location_id()
            market = new_location_id()
            cid = new_character_id()
            await uow.worlds.add(World(id=wid, name="Vale", seed_version="s2-test"))
            await uow.locations.add(Location(id=home, world_id=wid, name="Hearth", capacity=4))
            await uow.locations.add(Location(id=market, world_id=wid, name="Market", capacity=9))
            await uow.characters.add_identity(cid, wid, "Wren")
            await uow.characters.add_state(
                Character(
                    id=cid,
                    world_id=wid,
                    name="Wren",
                    card_version=1,
                    location_id=home,
                    stamina=stamina,
                    mana=mana,
                )
            )
            await uow.versions.ensure(cid, wid, "character")
            await uow.routes.add(
                TravelRoute(
                    id=new_route_id(),
                    world_id=wid,
                    from_location_id=home,
                    to_location_id=market,
                    duration_phases=2,
                    stamina_cost=10,
                )
            )
            await uow.commit()
            return {"world": wid, "home": home, "market": market, "wren": cid}
    finally:
        await engine.dispose()


async def _run_row(world_id: UUID, absolute: int) -> UUID:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            run_id = new_phase_run_id()
            await uow.phases.create_run(
                PhaseRun(id=run_id, world_id=world_id, absolute_index=absolute)
            )
            await uow.commit()
            return run_id
    finally:
        await engine.dispose()


def _orchestrator() -> Any:
    from worldsim.application.orchestration.stage1 import Stage1Orchestrator
    from worldsim.application.tasks.service import TaskService
    from worldsim.application.tracing.service import TraceService
    from worldsim.application.transactions.canonical import CanonicalTransaction
    from worldsim.infrastructure.tracing.langsmith import NullExporter

    engine = create_engine(Settings())
    factory = lambda: create_unit_of_work(engine)  # noqa: E731

    def _no_gateway(role: str) -> Any:
        raise AssertionError(f"tick must not call models: {role}")

    return Stage1Orchestrator(
        factory,
        CanonicalTransaction(factory),
        TaskService(factory),
        TraceService(factory, NullExporter()),
        _no_gateway,
        {},
    )


def test_start_guards(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_world()
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await start_activity(
                    uow,
                    ids["world"],
                    ids["wren"],
                    ActivityKind.WORK,
                    0,
                    duration_phases=3,
                )
            async with create_unit_of_work(engine) as uow:
                with pytest.raises(DomainError) as exc_info:
                    await start_activity(
                        uow,
                        ids["world"],
                        ids["wren"],
                        ActivityKind.REST,
                        0,
                        duration_phases=2,
                    )
                assert exc_info.value.code == ErrorCode.PRECONDITION_FAILED
            async with create_unit_of_work(engine) as uow:
                with pytest.raises(DomainError) as exc_info:
                    await start_activity(
                        uow,
                        ids["world"],
                        ids["wren"],
                        ActivityKind.TRAVEL,
                        0,
                        to_location_id=ids["home"],
                    )
                assert exc_info.value.code == ErrorCode.PRECONDITION_FAILED
        finally:
            await engine.dispose()

    _run(_inner())


def test_interrupt_resume_cancel_idempotent(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_world()
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                activity = await start_activity(
                    uow,
                    ids["world"],
                    ids["wren"],
                    ActivityKind.WORK,
                    0,
                    duration_phases=4,
                )
            async with create_unit_of_work(engine) as uow:
                first = await interrupt_activity(uow, activity.id, 2)
                assert (first.changed, first.activity.status) == (True, ActivityStatus.INTERRUPTED)
                assert first.activity.progress_phases == 2
                again = await interrupt_activity(uow, activity.id, 3)
                assert again.changed is False
            async with create_unit_of_work(engine) as uow:
                resumed = await resume_activity(uow, activity.id, 5)
                assert resumed.changed is True
                assert resumed.activity.start_absolute == 5
                assert resumed.activity.progress_phases == 2
            async with create_unit_of_work(engine) as uow:
                redundant = await resume_activity(uow, activity.id, 5)
                assert redundant.changed is False
                cancelled = await cancel_activity(uow, activity.id)
                assert cancelled.changed is True
                assert cancelled.activity.status == ActivityStatus.CANCELLED
                recancel = await cancel_activity(uow, activity.id)
                assert recancel.changed is False
        finally:
            await engine.dispose()

    _run(_inner())


def test_travel_completes_through_quiet_phases(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_world()
        orch = _orchestrator()
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                activity = await start_activity(
                    uow,
                    ids["world"],
                    ids["wren"],
                    ActivityKind.TRAVEL,
                    10,
                    to_location_id=ids["market"],
                )
                assert activity.duration_phases == 2
            # In-progress ticks write nothing and call no models.
            assert (
                await orch._advance_activities(ids["world"], await _run_row(ids["world"], 11), 11)
                == 0
            )
            async with create_unit_of_work(engine) as uow:
                wren = await uow.characters.get(ids["wren"])
                assert wren.location_id == ids["home"]
                assert wren.stamina == 80
            # Due tick moves Wren and spends the leg cost.
            assert (
                await orch._advance_activities(ids["world"], await _run_row(ids["world"], 12), 12)
                == 1
            )
            async with create_unit_of_work(engine) as uow:
                wren = await uow.characters.get(ids["wren"])
                assert wren.location_id == ids["market"]
                assert wren.stamina == 70
                done = await uow.activities.get(activity.id)
                assert done.status == ActivityStatus.COMPLETED
        finally:
            await engine.dispose()

    _run(_inner())


def test_rest_recovers_and_patrol_observes(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_world(stamina=20, mana=10)
        orch = _orchestrator()
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                rest = await start_activity(
                    uow,
                    ids["world"],
                    ids["wren"],
                    ActivityKind.REST,
                    0,
                    duration_phases=2,
                )
            assert (
                await orch._advance_activities(ids["world"], await _run_row(ids["world"], 2), 2)
                == 1
            )
            async with create_unit_of_work(engine) as uow:
                wren = await uow.characters.get(ids["wren"])
                assert (wren.stamina, wren.mana) == (40, 20)
                assert (await uow.activities.get(rest.id)).status == ActivityStatus.COMPLETED
            async with create_unit_of_work(engine) as uow:
                patrol = await start_activity(
                    uow,
                    ids["world"],
                    ids["wren"],
                    ActivityKind.PATROL,
                    2,
                    duration_phases=1,
                )
            assert (
                await orch._advance_activities(ids["world"], await _run_row(ids["world"], 3), 3)
                == 1
            )
            async with create_unit_of_work(engine) as uow:
                observations = await uow.perception.observations_for_observer(ids["wren"])
                assert any(
                    fact.key == "patrol:Hearth" for obs in observations for fact in obs.facts
                )
                assert (await uow.activities.get(patrol.id)).status == ActivityStatus.COMPLETED
        finally:
            await engine.dispose()

    _run(_inner())


def test_exhausted_traveler_stalls(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_world(stamina=5)
        orch = _orchestrator()
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                activity = await start_activity(
                    uow,
                    ids["world"],
                    ids["wren"],
                    ActivityKind.TRAVEL,
                    0,
                    to_location_id=ids["market"],
                )
            assert (
                await orch._advance_activities(ids["world"], await _run_row(ids["world"], 2), 2)
                == 0
            )
            async with create_unit_of_work(engine) as uow:
                stalled = await uow.activities.get(activity.id)
                assert stalled.status == ActivityStatus.INTERRUPTED
                wren = await uow.characters.get(ids["wren"])
                assert wren.location_id == ids["home"]
                assert wren.stamina == 5
        finally:
            await engine.dispose()

    _run(_inner())


def test_effective_progress_derives_from_clock() -> None:
    from worldsim.domain.activities import Activity

    activity = Activity(
        id="00000000-0000-4000-8000-000000000001",  # type: ignore[assignment]
        world_id="00000000-0000-4000-8000-000000000002",  # type: ignore[assignment]
        character_id="00000000-0000-4000-8000-000000000003",  # type: ignore[assignment]
        kind=ActivityKind.WORK,
        status=ActivityStatus.ACTIVE,
        start_absolute=10,
        duration_phases=4,
    )
    assert effective_progress(activity, 10) == 0
    assert effective_progress(activity, 12) == 2
    assert effective_progress(activity, 99) == 4
    frozen = activity.model_copy(update={"status": ActivityStatus.INTERRUPTED})
    assert effective_progress(frozen, 99) == 0


ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def client(migrated_db: None) -> Iterator[ApiClient]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=ROOT / "content" / "seeds" / "stage0",
        migrations_dir=ROOT / "backend" / "migrations",
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw)


def test_activity_endpoints_round_trip(client: ApiClient) -> None:
    headers = {"X-Worldsim-Role": "watcher"}
    ids = _run(_seed_world())
    started = client.post(
        "/api/v1/stage2/activities",
        json={
            "world_id": str(ids["world"]),
            "character_id": str(ids["wren"]),
            "kind": "travel",
            "to_location_id": str(ids["market"]),
        },
        headers=headers,
    )
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["status"] == "active" and body["duration_phases"] == 2
    listed = client.get(
        "/api/v1/stage2/activities",
        params={"world_id": str(ids["world"])},
        headers=headers,
    )
    assert [m["id"] for m in listed.json()["members"]] == [body["id"]]
    interrupted = client.post(f"/api/v1/stage2/activities/{body['id']}/interrupt", headers=headers)
    assert interrupted.json()["status"] == "interrupted"
    resumed = client.post(f"/api/v1/stage2/activities/{body['id']}/resume", headers=headers)
    assert resumed.json()["status"] == "active"
    cancelled = client.post(f"/api/v1/stage2/activities/{body['id']}/cancel", headers=headers)
    assert cancelled.json()["status"] == "cancelled"
    assert (
        client.get(
            "/api/v1/stage2/activities",
            params={"world_id": str(ids["world"])},
            headers=headers,
        ).json()["members"]
        == []
    )
