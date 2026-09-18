"""Revamp P09: persistent conditions, multi-step direction, confrontation rules."""

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


def _deity() -> dict[str, str]:
    return {"X-Worldsim-Role": "deity"}


@pytest.fixture
def world_ids(migrated_db: None) -> dict[str, UUID]:
    ids = asyncio.run(_seed_two())

    async def _legs() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                characters = await uow.characters.list_for_world(ids["world"])
                home = next(c.location_id for c in characters if c.id == ids["wren"])
                away = next(c.location_id for c in characters if c.id == ids["ash"])
                for origin, dest in ((away, home), (home, away)):
                    await uow.routes.add(
                        TravelRoute(
                            id=new_route_id(),
                            world_id=ids["world"],
                            from_location_id=origin,
                            to_location_id=dest,
                            duration_phases=1,
                            stamina_cost=5,
                        )
                    )
                await uow.commit()
                ids["hearth"] = home
                ids["market"] = away
        finally:
            await engine.dispose()

    asyncio.run(_legs())
    return ids


def _gateway_for(plan: dict[str, Any] | None, ids: dict[str, UUID], max_index: int) -> FakeGateway:
    snapshots = {i: derive_snapshot_id(derive_run_id(ids["world"], i)) for i in range(1, max_index + 1)}
    base = _base_route_for(ids, snapshots)
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)

    def route(request: Any) -> Any:
        if "game-master" in (request.system or ""):
            time.sleep(0.1)
            return json.dumps(plan) if plan is not None else None
        return base(request)

    gateway.route = route
    return gateway


def _plague_plan(market: UUID) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "steps": [
            {
                "kind": "world_condition",
                "explanation": "A strange cough spreads at the market",
                "label": "Ashen cough",
                "detail": "unknown cause",
                "location_ids": [str(market)],
                "severity": 2,
                "duration_phases": 2,
            }
        ],
        "clarification": "",
    }


async def _stamina(world_id: UUID, character_id: UUID) -> int:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            return (await uow.characters.get(character_id)).stamina
    finally:
        await engine.dispose()


def test_plague_persists_ticks_and_recovers(world_ids: dict[str, UUID]) -> None:
    ids = world_ids
    gateway = _gateway_for(_plague_plan(ids["market"]), ids, 5)

    async def _inner() -> None:
        app = create_app(
            Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://p09") as client:
            created = await client.post(
                "/api/v1/interventions",
                json={
                    "world_id": str(ids["world"]),
                    "client_request_id": "p09-plague-1",
                    "text": "An unknown devastating plague at the market",
                    "mode": "force",
                    "scope": {"kind": "locations", "location_ids": [str(ids["market"])]},
                    "effective_at": "next_boundary",
                },
                headers=_deity(),
            )
            assert created.json()["status"] == "queued", created.text
            ash_before = await _stamina(ids["world"], ids["ash"])
            wren_before = await _stamina(ids["world"], ids["wren"])
            first = await client.post(
                "/api/v1/stage1/advance",
                json={"world_id": str(ids["world"]), "absolute_index": 1},
                headers=_watcher(),
            )
            assert first.status_code == 200, first.text

            conditions = await client.get(
                "/api/v1/world/conditions",
                params={"world_id": str(ids["world"])},
                headers=_watcher(),
            )
            assert conditions.status_code == 200, conditions.text
            assert len(conditions.json()["conditions"]) == 1
            assert conditions.json()["conditions"][0]["status"] == "active"

            assert await _stamina(ids["world"], ids["ash"]) == ash_before - 2
            assert await _stamina(ids["world"], ids["wren"]) == wren_before

            chronicle = await client.get(
                "/api/v1/world/chronicle",
                params={"world_id": str(ids["world"]), "after": 0, "limit": 50},
                headers=_watcher(),
            )
            assert any(e["event_type"] == "condition_tick" for e in chronicle.json()["entries"])

            replay = await client.post(
                "/api/v1/stage1/advance",
                json={"world_id": str(ids["world"]), "absolute_index": 1},
                headers=_watcher(),
            )
            assert replay.json()["duplicate"] is True
            assert await _stamina(ids["world"], ids["ash"]) == ash_before - 2
            macro = await client.post(
                "/api/v1/macro/advance",
                json={"world_id": str(ids["world"]), "day": 1, "resolution": "day"},
                headers=_watcher(),
            )
            assert macro.status_code == 409, macro.text

            for index in (2, 3):
                advance = await client.post(
                    "/api/v1/stage1/advance",
                    json={"world_id": str(ids["world"]), "absolute_index": index},
                    headers=_watcher(),
                )
                assert advance.status_code == 200, advance.text
            assert await _stamina(ids["world"], ids["ash"]) == ash_before - 6

            fourth = await client.post(
                "/api/v1/stage1/advance",
                json={"world_id": str(ids["world"]), "absolute_index": 4},
                headers=_watcher(),
            )
            assert fourth.status_code == 200, fourth.text
            recovered = await client.get(
                "/api/v1/world/conditions",
                params={"world_id": str(ids["world"])},
                headers=_watcher(),
            )
            assert recovered.json()["conditions"][0]["status"] == "recovered"

    asyncio.run(_inner())


def test_multi_leg_journey_progresses(world_ids: dict[str, UUID]) -> None:
    ids = world_ids
    plan = {
        "schema_version": 1,
        "steps": [
            {
                "kind": "direct_activity",
                "explanation": "Ash to Hearth",
                "character_id": str(ids["ash"]),
                "activity": "travel",
                "to_location_id": str(ids["hearth"]),
            },
            {
                "kind": "direct_activity",
                "explanation": "Ash back to Market",
                "character_id": str(ids["ash"]),
                "activity": "travel",
                "to_location_id": str(ids["market"]),
            },
        ],
        "clarification": "",
    }
    gateway = _gateway_for(plan, ids, 4)

    async def _inner() -> None:
        app = create_app(
            Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://p09") as client:
            created = await client.post(
                "/api/v1/interventions",
                json={
                    "world_id": str(ids["world"]),
                    "client_request_id": "p09-legs-1",
                    "text": "Ash goes to Hearth then back to the Market",
                    "mode": "force",
                    "scope": {"kind": "characters", "character_ids": [str(ids["ash"])]},
                    "effective_at": "next_boundary",
                },
                headers=_deity(),
            )
            assert created.json()["status"] == "queued", created.text

            first = await client.post(
                "/api/v1/stage1/advance",
                json={"world_id": str(ids["world"]), "absolute_index": 1},
                headers=_watcher(),
            )
            assert first.status_code == 200, first.text
            item = await client.get(
                f"/api/v1/interventions/{created.json()['id']}", headers=_deity()
            )
            assert item.json()["status"] == "executing", item.text

            second = await client.post(
                "/api/v1/stage1/advance",
                json={"world_id": str(ids["world"]), "absolute_index": 2},
                headers=_watcher(),
            )
            assert second.status_code == 200, second.text
            mid = await client.get(
                f"/api/v1/interventions/{created.json()['id']}", headers=_deity()
            )
            assert mid.json()["status"] == "executing", mid.text

            third = await client.post(
                "/api/v1/stage1/advance",
                json={"world_id": str(ids["world"]), "absolute_index": 3},
                headers=_watcher(),
            )
            assert third.status_code == 200, third.text
            done = await client.get(
                f"/api/v1/interventions/{created.json()['id']}", headers=_deity()
            )
            assert done.json()["status"] == "completed", done.text
            assert all(s["status"] == "completed" for s in done.json()["steps"])

    asyncio.run(_inner())


def test_distant_spar_fails_with_travel_first(world_ids: dict[str, UUID]) -> None:
    ids = world_ids
    plan = {
        "schema_version": 1,
        "steps": [
            {
                "kind": "direct_attempt",
                "explanation": "Wren spars Ash from afar",
                "character_id": str(ids["wren"]),
                "family": "spar",
                "action": {
                    "family": "spar",
                    "character_id": str(ids["wren"]),
                    "snapshot_id": "00000000-0000-4000-8000-000000000000",
                    "target_character_id": str(ids["ash"]),
                },
            }
        ],
        "clarification": "",
    }
    gateway = _gateway_for(plan, ids, 2)

    async def _inner() -> None:
        app = create_app(
            Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://p09") as client:
            created = await client.post(
                "/api/v1/interventions",
                json={
                    "world_id": str(ids["world"]),
                    "client_request_id": "p09-spar-1",
                    "text": "Wren spars Ash",
                    "mode": "force",
                    "scope": {"kind": "characters", "character_ids": [str(ids["wren"])]},
                    "effective_at": "next_boundary",
                },
                headers=_deity(),
            )
            advance = await client.post(
                "/api/v1/stage1/advance",
                json={"world_id": str(ids["world"]), "absolute_index": 1},
                headers=_watcher(),
            )
            assert advance.status_code == 200, advance.text
            done = await client.get(
                f"/api/v1/interventions/{created.json()['id']}", headers=_deity()
            )
            assert done.json()["status"] == "failed", done.text
            assert "travel first" in done.json()["steps"][0]["failure_reason"]

    asyncio.run(_inner())


def test_mid_sequence_cancel_preserves_history(world_ids: dict[str, UUID]) -> None:
    ids = world_ids
    plan = {
        "schema_version": 1,
        "steps": [
            {
                "kind": "direct_activity",
                "explanation": "Ash rests",
                "character_id": str(ids["ash"]),
                "activity": "rest",
            },
            {
                "kind": "direct_activity",
                "explanation": "Ash trains",
                "character_id": str(ids["ash"]),
                "activity": "train",
            },
        ],
        "clarification": "",
    }
    gateway = _gateway_for(plan, ids, 2)

    async def _inner() -> None:
        app = create_app(
            Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://p09") as client:
            created = await client.post(
                "/api/v1/interventions",
                json={
                    "world_id": str(ids["world"]),
                    "client_request_id": "p09-partial-1",
                    "text": "Ash rests then trains",
                    "mode": "force",
                    "scope": {"kind": "characters", "character_ids": [str(ids["ash"])]},
                    "effective_at": "next_boundary",
                },
                headers=_deity(),
            )
            # Rest starts; train cannot start while rest is active, so it fails.
            advance = await client.post(
                "/api/v1/stage1/advance",
                json={"world_id": str(ids["world"]), "absolute_index": 1},
                headers=_watcher(),
            )
            assert advance.status_code == 200, advance.text
            item = await client.get(
                f"/api/v1/interventions/{created.json()['id']}", headers=_deity()
            )
            assert item.json()["status"] == "partially_completed", item.text
            cancelled = await client.post(
                f"/api/v1/interventions/{created.json()['id']}/cancel",
                json={"expected_version": item.json()["version"]},
                headers=_deity(),
            )
            assert cancelled.json()["status"] == "cancelled", cancelled.text
            kept = [s for s in cancelled.json()["steps"] if s["status"] == "completed"]
            assert len(kept) == 1

    asyncio.run(_inner())
