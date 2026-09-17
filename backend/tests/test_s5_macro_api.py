"""Stage 5 macro HTTP API tests: reads, gates, advance."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.ids import (
    new_card_id,
    new_character_id,
    new_location_id,
    new_schedule_id,
    new_world_id,
)
from worldsim.domain.macro import LineageCharacter
from worldsim.domain.schedules import ScheduledEffect
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


@pytest.fixture
def client(migrated_db: None) -> TestClient:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield raw


def _seed() -> dict[str, UUID]:
    async def _inner() -> dict[str, UUID]:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            async with factory() as uow:
                wid = new_world_id()
                home = new_location_id()
                bram = new_character_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.locations.add(Location(id=home, world_id=wid, name="Hearth"))
                await uow.characters.add_identity(bram, wid, "Bram")
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=bram, name="Bram")
                )
                await uow.characters.add_state(
                    Character(
                        id=bram, world_id=wid, name="Bram", card_version=1,
                        location_id=home, stamina=80, mana=40,
                    )
                )
                await uow.versions.ensure(wid, wid, "world")
                await uow.versions.ensure(bram, wid, "character")
                await uow.lineage.put_record(
                    LineageCharacter(
                        character_id=bram, world_id=wid,
                        birth_absolute=0, succession_eligible=True,
                    )
                )
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(), world_id=wid, due_absolute=5,
                        kind="note", payload={"text": "market opens"},
                    )
                )
                await uow.commit()
                return {"world": wid, "home": home, "bram": bram}
        finally:
            await engine.dispose()

    return _run(_inner())


HEADERS = {"X-Worldsim-Role": "watcher"}


def test_runs_advance_and_reads(client: TestClient) -> None:
    ids = _seed()
    wid = str(ids["world"])

    empty = client.get("/api/v1/macro/runs", params={"world_id": wid}, headers=HEADERS)
    assert empty.status_code == 200 and empty.json()["runs"] == []

    advance = client.post(
        "/api/v1/macro/advance",
        json={"world_id": wid, "day": 1, "resolution": "week"},
        headers=HEADERS,
    )
    assert advance.status_code == 200, advance.text
    body = advance.json()
    assert body["state"] == "completed" and body["duplicate"] is False

    runs = client.get("/api/v1/macro/runs", params={"world_id": wid}, headers=HEADERS)
    assert runs.status_code == 200
    (run,) = runs.json()["runs"]
    assert run["start_absolute"] == 0 and run["end_absolute"] == 70
    kinds = sorted(e["kind"] for e in run["effects"])
    assert kinds == ["clock_advance", "schedule_progress"]

    lineage = client.get("/api/v1/macro/lineage", params={"world_id": wid}, headers=HEADERS)
    assert lineage.status_code == 200
    (record,) = lineage.json()["records"]
    assert record["name"] == "Bram" and record["birth_absolute"] == 0

    focus = client.get("/api/v1/macro/focus", params={"world_id": wid}, headers=HEADERS)
    assert focus.status_code == 200 and focus.json()["assignments"] == []

    endings = client.get("/api/v1/macro/endings", params={"world_id": wid}, headers=HEADERS)
    assert endings.status_code == 200 and endings.json()["endings"] == []

    eras = client.get(
        "/api/v1/macro/eras",
        params={"world_id": wid, "start_absolute": 0, "end_absolute": 70},
        headers=HEADERS,
    )
    assert eras.status_code == 200 and eras.json()["eras"] == []


def test_advance_rejects_player_and_bad_resolution(client: TestClient) -> None:
    ids = _seed()
    wid = str(ids["world"])
    player = {
        "X-Worldsim-Role": "player",
        "X-Worldsim-Character": str(ids["bram"]),
    }
    denied = client.post(
        "/api/v1/macro/advance",
        json={"world_id": wid, "day": 1, "resolution": "day"},
        headers=player,
    )
    assert denied.status_code == 403

    bad = client.post(
        "/api/v1/macro/advance",
        json={"world_id": wid, "day": 1, "resolution": "eon"},
        headers=HEADERS,
    )
    assert bad.status_code in (400, 422)

    allowed = client.get("/api/v1/macro/runs", params={"world_id": wid}, headers=player)
    assert allowed.status_code == 200
