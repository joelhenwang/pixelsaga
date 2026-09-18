"""Revamp P07: durable interventions and typed execution."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from test_stage1_api import _route_for as _base_route_for  # pyright: ignore[reportPrivateUsage]
from test_stage1_api import _seed_two  # pyright: ignore[reportPrivateUsage]
from test_stage1_api import ApiClient
from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
from worldsim.domain.activities import TravelRoute
from worldsim.domain.ids import new_route_id
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"


def _watcher() -> dict[str, str]:
    return {"X-Worldsim-Role": "watcher"}


def _director() -> dict[str, str]:
    return {"X-Worldsim-Role": "director"}


def _deity() -> dict[str, str]:
    return {"X-Worldsim-Role": "deity"}


def _travel_plan(ash: UUID, market: UUID) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "steps": [
            {
                "kind": "direct_activity",
                "explanation": "Ash walks to Hearth",
                "character_id": str(ash),
                "activity": "travel",
                "to_location_id": str(market),
            }
        ],
        "clarification": "",
    }


def _app_with(gateway: FakeGateway) -> Any:
    return create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )


@pytest.fixture
def seeded_ids(migrated_db: None) -> dict[str, UUID]:
    ids = asyncio.run(_seed_two())

    async def _leg() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                characters = await uow.characters.list_for_world(ids["world"])
                home = next(c.location_id for c in characters if c.id == ids["wren"])
                away = next(c.location_id for c in characters if c.id == ids["ash"])
                await uow.routes.add(
                    TravelRoute(
                        id=new_route_id(),
                        world_id=ids["world"],
                        from_location_id=away,
                        to_location_id=home,
                        duration_phases=2,
                        stamina_cost=10,
                    )
                )
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(_leg())
    return ids


def test_force_travel_queued_then_applied_once(seeded_ids: dict[str, UUID]) -> None:
    ids = seeded_ids
    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    base = _base_route_for(ids, snapshots)
    characters = asyncio.run(_character_places(ids["world"]))
    hearth = characters["hearth"]

    def route(request: Any) -> Any:
        if "game-master" in (request.system or ""):
            time.sleep(0.2)
            return json.dumps(_travel_plan(ids["ash"], hearth))
        return base(request)

    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = route

    async def _inner() -> None:
        transport = httpx.ASGITransport(app=_app_with(gateway))
        async with httpx.AsyncClient(transport=transport, base_url="http://p07") as client:
            body = {
                "world_id": str(ids["world"]),
                "client_request_id": "p07-travel-1",
                "text": "Ash should go to Hearth",
                "mode": "force",
                "scope": {"kind": "characters", "character_ids": [str(ids["ash"])]},
                "effective_at": "next_boundary",
            }
            first = await client.post("/api/v1/interventions", json=body, headers=_deity())
            assert first.status_code == 200, first.text
            assert first.json()["status"] == "queued"
            replay = await client.post("/api/v1/interventions", json=body, headers=_deity())
            assert replay.json()["id"] == first.json()["id"]

            advance = await client.post(
                "/api/v1/stage1/advance",
                json={"world_id": str(ids["world"]), "absolute_index": 1},
                headers=_watcher(),
            )
            assert advance.status_code == 200, advance.text

            done = await client.get(
                f"/api/v1/interventions/{first.json()['id']}", headers=_deity()
            )
            assert done.json()["status"] == "completed", done.text

            activities = await client.get(
                "/api/v1/stage2/activities",
                params={"world_id": str(ids["world"])},
                headers=_watcher(),
            )
            ash_active = [
                a for a in activities.json()["members"] if a["character_id"] == str(ids["ash"])
            ]
            assert len(ash_active) == 1
            assert ash_active[0]["to_location_id"] == str(hearth)

    asyncio.run(_inner())


async def _character_places(world_id: UUID) -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            characters = await uow.characters.list_for_world(world_id)
            locations = {loc.id: loc.name for loc in await uow.locations.list_for_world(world_id)}
            out: dict[str, UUID] = {}
            for character in characters:
                out[locations[character.location_id].lower()] = character.location_id
            return out
    finally:
        await engine.dispose()


def test_director_cannot_force(seeded_ids: dict[str, UUID]) -> None:
    ids = seeded_ids
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = lambda request: json.dumps(_travel_plan(ids["ash"], ids["wren"]))

    async def _inner() -> None:
        transport = httpx.ASGITransport(app=_app_with(gateway))
        async with httpx.AsyncClient(transport=transport, base_url="http://p07") as client:
            response = await client.post(
                "/api/v1/interventions",
                json={
                    "world_id": str(ids["world"]),
                    "client_request_id": "p07-force-no",
                    "text": "Ash should go to Hearth",
                    "mode": "force",
                    "scope": {"kind": "characters", "character_ids": [str(ids["ash"])]},
                    "effective_at": "next_boundary",
                },
                headers=_director(),
            )
            assert response.status_code == 403, response.text

    asyncio.run(_inner())


def test_ambiguous_names_need_clarification(migrated_db: None) -> None:
    from fastapi.testclient import TestClient

    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = lambda request: None
    app = _app_with(gateway)
    with TestClient(app) as raw:
        client = ApiClient(raw)
        world = raw.post("/api/v1/world/seed").json()["world_id"]
        first = client.post(
            "/api/v1/stage1/characters",
            json={"world_id": world, "name": "Ash", "location_id": "10000000-0000-4000-8000-000000000011"},
            headers=_watcher(),
        )
        assert first.status_code == 200, first.text
        response = client.post(
            "/api/v1/interventions",
            json={
                "world_id": world,
                "client_request_id": "p07-ash-ash",
                "text": "Start a confrontation between Ash and Ash",
                "mode": "force",
                "scope": {"kind": "world"},
                "effective_at": "next_boundary",
            },
            headers=_deity(),
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "needs_clarification"


def test_cancel_unclaimed_changes_no_canon(seeded_ids: dict[str, UUID]) -> None:
    ids = seeded_ids
    characters = asyncio.run(_character_places(ids["world"]))
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = lambda request: json.dumps(_travel_plan(ids["ash"], characters["hearth"]))

    async def _inner() -> None:
        transport = httpx.ASGITransport(app=_app_with(gateway))
        async with httpx.AsyncClient(transport=transport, base_url="http://p07") as client:
            created = await client.post(
                "/api/v1/interventions",
                json={
                    "world_id": str(ids["world"]),
                    "client_request_id": "p07-cancel-1",
                    "text": "Ash should go to Hearth",
                    "mode": "force",
                    "scope": {"kind": "characters", "character_ids": [str(ids["ash"])]},
                    "effective_at": "next_boundary",
                },
                headers=_deity(),
            )
            item = created.json()
            cancelled = await client.post(
                f"/api/v1/interventions/{item['id']}/cancel",
                json={"expected_version": item["version"]},
                headers=_deity(),
            )
            assert cancelled.json()["status"] == "cancelled", cancelled.text
            activities = await client.get(
                "/api/v1/stage2/activities",
                params={"world_id": str(ids["world"])},
                headers=_watcher(),
            )
            assert activities.json()["members"] == []

    asyncio.run(_inner())


def test_unsupported_fight_is_explicit(seeded_ids: dict[str, UUID]) -> None:
    ids = seeded_ids

    def route(request: Any) -> Any:
        if "game-master" in (request.system or ""):
            return json.dumps({"schema_version": 1, "steps": [], "clarification": "lethal combat is unsupported; offer a sparring bout"})
        return None

    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = route

    async def _inner() -> None:
        transport = httpx.ASGITransport(app=_app_with(gateway))
        async with httpx.AsyncClient(transport=transport, base_url="http://p07") as client:
            response = await client.post(
                "/api/v1/interventions",
                json={
                    "world_id": str(ids["world"]),
                    "client_request_id": "p07-fight-1",
                    "text": "Start a lethal fight between Wren and Ash",
                    "mode": "force",
                    "scope": {"kind": "characters", "character_ids": [str(ids["wren"]), str(ids["ash"])]},
                    "effective_at": "next_boundary",
                },
                headers=_deity(),
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "needs_clarification"
            assert "sparring" in response.json()["failure_reason"]

    asyncio.run(_inner())


def test_director_hook_proposal_applies_at_boundary(seeded_ids: dict[str, UUID]) -> None:
    ids = seeded_ids
    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    base = _base_route_for(ids, snapshots)

    def route(request: Any) -> Any:
        if "game-master" in (request.system or ""):
            return json.dumps(
                {
                    "schema_version": 1,
                    "steps": [
                        {
                            "kind": "propose_hook",
                            "explanation": "toll tension",
                            "title": "Trouble on the bridge road",
                            "purpose": "the tolls spark a dispute",
                            "participant_ids": [str(ids["ash"])],
                        }
                    ],
                    "clarification": "",
                }
            )
        return base(request)

    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = route

    async def _inner() -> None:
        transport = httpx.ASGITransport(app=_app_with(gateway))
        async with httpx.AsyncClient(transport=transport, base_url="http://p07") as client:
            created = await client.post(
                "/api/v1/interventions",
                json={
                    "world_id": str(ids["world"]),
                    "client_request_id": "p07-hook-1",
                    "text": "Introduce trouble on the bridge road",
                    "mode": "influence",
                    "scope": {"kind": "characters", "character_ids": [str(ids["ash"])]},
                    "effective_at": "next_boundary",
                },
                headers=_director(),
            )
            assert created.json()["status"] == "queued", created.text
            advance = await client.post(
                "/api/v1/stage1/advance",
                json={"world_id": str(ids["world"]), "absolute_index": 1},
                headers=_watcher(),
            )
            assert advance.status_code == 200, advance.text
            hooks = await client.get(
                "/api/v1/stage2/director/hooks",
                params={"world_id": str(ids["world"])},
                headers=_director(),
            )
            titles = [h["title"] for h in hooks.json()["hooks"]]
            assert "Trouble on the bridge road" in titles

    asyncio.run(_inner())
