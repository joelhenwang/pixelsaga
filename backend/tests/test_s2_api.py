"""Stage 2 reads: role filtering and stale conflicts (owned by S2-API-001)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.domain.characters import Character
from worldsim.domain.ids import new_character_id, new_location_id, new_world_id
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


async def _seed_realm() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            hearth = new_location_id()
            market = new_location_id()
            wren = new_character_id()
            ash = new_character_id()
            await uow.worlds.add(World(id=wid, name="Vale", seed_version="s2-test"))
            await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth", capacity=4))
            await uow.locations.add(
                Location(
                    id=market,
                    world_id=wid,
                    name="Market",
                    capacity=9,
                    discovered=False,
                )
            )
            for cid, name, place in ((wren, "Wren", hearth), (ash, "Ash", market)):
                await uow.characters.add_identity(cid, wid, name)
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=wid,
                        name=name,
                        card_version=1,
                        location_id=place,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
            await uow.commit()
            return {
                "world": wid,
                "hearth": hearth,
                "market": market,
                "wren": wren,
                "ash": ash,
            }
    finally:
        await engine.dispose()


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


def test_timeline_and_map_filter_by_role(client: ApiClient) -> None:
    watcher = {"X-Worldsim-Role": "watcher"}
    ids = _run(_seed_realm())
    timeline = client.get(
        "/api/v1/stage2/timeline",
        params={"world_id": str(ids["world"])},
        headers=watcher,
    )
    assert timeline.status_code == 200, timeline.text
    assert timeline.json()["total"] == 0
    assert timeline.json()["entries"] == []
    world_map = client.get(
        "/api/v1/stage2/map",
        params={"world_id": str(ids["world"])},
        headers=watcher,
    )
    assert [p["name"] for p in world_map.json()["places"]] == ["Hearth", "Market"]
    hearth = next(p for p in world_map.json()["places"] if p["name"] == "Hearth")
    assert hearth["occupants"] == ["Wren"]
    player = {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(ids["wren"])}
    player_map = client.get(
        "/api/v1/stage2/map",
        params={"world_id": str(ids["world"])},
        headers=player,
    )
    assert [p["name"] for p in player_map.json()["places"]] == ["Hearth"]


def test_diary_and_hooks_stay_scoped(client: ApiClient) -> None:
    watcher = {"X-Worldsim-Role": "watcher"}
    ids = _run(_seed_realm())
    diary = client.get(f"/api/v1/stage2/characters/{ids['wren']}/diary", headers=watcher)
    assert diary.status_code == 200, diary.text
    assert diary.json()["observations"] == []
    player = {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(ids["ash"])}
    denied = client.get(f"/api/v1/stage2/characters/{ids['wren']}/diary", headers=player)
    assert denied.status_code == 403, denied.text
    hooks_denied = client.get(
        "/api/v1/stage2/director/hooks",
        params={"world_id": str(ids["world"])},
        headers=player,
    )
    assert hooks_denied.status_code == 403, hooks_denied.text
    hooks = client.get(
        "/api/v1/stage2/director/hooks",
        params={"world_id": str(ids["world"])},
        headers=watcher,
    )
    assert hooks.json()["hooks"] == [] and hooks.json()["arcs"] == []


def test_operations_status_counts(client: ApiClient) -> None:
    watcher = {"X-Worldsim-Role": "watcher"}
    ids = _run(_seed_realm())
    status = client.get(
        "/api/v1/stage2/operations/status",
        params={"world_id": str(ids["world"])},
        headers=watcher,
    )
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["open_run_id"] is None
    assert body["pending_outbox"] == 0
    assert body["total_events"] == 0


def test_stale_transfer_conflicts_cleanly(client: ApiClient) -> None:
    from worldsim.application.commands.inventory import give_item
    from worldsim.domain.items import load_item_definitions

    watcher = {"X-Worldsim-Role": "watcher"}
    ids = _run(_seed_realm())
    catalog = load_item_definitions(ROOT / "content" / "definitions" / "items.json")

    async def _give() -> UUID:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                item = await give_item(uow, "watcher", ids["world"], "rope", ids["wren"], catalog)
                return item.id
        finally:
            await engine.dispose()

    item_id = _run(_give())
    moved = client.post(
        f"/api/v1/stage2/items/{item_id}/transfer",
        json={"to_owner_id": None},
        headers=watcher,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["version"] == 1

    async def _stale() -> str:
        from worldsim.domain.errors import DomainError

        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                item = await uow.inventory.get_item(item_id)
                try:
                    await uow.inventory.save_item(
                        item.model_copy(update={"owner_id": ids["wren"]}), 0
                    )
                except DomainError as exc:
                    return exc.code.value
                return "no-conflict"
        finally:
            await engine.dispose()

    assert _run(_stale()) == "version_conflict"
