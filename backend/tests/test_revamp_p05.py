"""Revamp P05: projection scoping, travel data, cursor stability."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"

WORLD = UUID("10000000-0000-4000-8000-000000000001")
WREN = UUID("10000000-0000-4000-8000-000000000101")
ASH = UUID("10000000-0000-4000-8000-000000000102")
HEARTH = UUID("10000000-0000-4000-8000-000000000011")
MARKET = UUID("10000000-0000-4000-8000-000000000012")


@pytest.fixture
def client(migrated_db: None) -> Iterator[ApiClient]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = lambda request: None
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        seeded = raw.post("/api/v1/world/seed")
        assert seeded.status_code == 200, seeded.text
        yield ApiClient(raw)


def _watcher() -> dict[str, str]:
    return {"X-Worldsim-Role": "watcher"}


def _deity() -> dict[str, str]:
    return {"X-Worldsim-Role": "deity"}


def _player(character: UUID) -> dict[str, str]:
    return {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(character)}


def test_player_presentation_hides_threads(client: ApiClient) -> None:
    response = client.get(
        "/api/v1/world/presentation", params={"world_id": str(WORLD)}, headers=_player(WREN)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["capabilities"]["role"] == "player"
    assert body["threads"] == []
    assert body["manifest"]["schematic"] is False
def test_travel_activity_carries_route_projection(client: ApiClient) -> None:
    async def _leg() -> None:
        from worldsim.domain.activities import TravelRoute
        from worldsim.domain.ids import new_route_id
        from worldsim.infrastructure.db.engine import create_engine
        from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
        from worldsim.infrastructure.settings import Settings

        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await uow.routes.add(
                    TravelRoute(
                        id=new_route_id(),
                        world_id=WORLD,
                        from_location_id=HEARTH,
                        to_location_id=MARKET,
                        duration_phases=2,
                        stamina_cost=10,
                    )
                )
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(_leg())
    started = client.post(
        "/api/v1/stage2/activities",
        json={"world_id": str(WORLD), "character_id": str(WREN), "kind": "travel", "to_location_id": str(MARKET)},
        headers=_deity(),
    )
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["from_location_id"] == str(HEARTH)
    assert body["to_location_id"] == str(MARKET)
    assert body["route_id"] is not None
    assert body["effective_progress_phases"] == 0

    snapshot = client.get(
        "/api/v1/world/presentation", params={"world_id": str(WORLD)}, headers=_watcher()
    )
    assert snapshot.status_code == 200, snapshot.text
    activities = snapshot.json()["activities"]
    assert len(activities) == 1
    assert activities[0]["to_location_id"] == str(MARKET)


def test_empty_chronicle_page_still_advances(client: ApiClient) -> None:
    first = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(WORLD), "after": 0, "limit": 20},
        headers=_player(ASH),
    )
    assert first.status_code == 200, first.text
    cursor = first.json()["next_after"]
    second = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(WORLD), "after": cursor, "limit": 20},
        headers=_player(ASH),
    )
    assert second.status_code == 200, second.text
    assert second.json()["entries"] == []
    assert second.json()["next_after"] == cursor
    assert second.json()["has_more"] is False
