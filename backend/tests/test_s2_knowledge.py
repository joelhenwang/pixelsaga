"""Claims and beliefs: eligibility, divergence, canon safety (owned by S2-KNOW-001)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.application.commands.knowledge import assert_claim
from worldsim.domain.characters import Character
from worldsim.domain.ids import new_character_id, new_location_id, new_world_id
from worldsim.domain.knowledge import (
    contradict,
    normalize,
    reinforce,
)
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


async def _seed_rooms() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            hearth = new_location_id()
            market = new_location_id()
            wren = new_character_id()
            ash = new_character_id()
            bram = new_character_id()
            await uow.worlds.add(World(id=wid, name="Vale", seed_version="s2-test"))
            await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth", capacity=4))
            await uow.locations.add(Location(id=market, world_id=wid, name="Market", capacity=9))
            for cid, name, place in (
                (wren, "Wren", hearth),
                (ash, "Ash", hearth),
                (bram, "Bram", market),
            ):
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
                "bram": bram,
            }
    finally:
        await engine.dispose()


def test_listeners_diverge_by_position(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_rooms()
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                claim = await assert_claim(
                    uow,
                    "watcher",
                    ids["world"],
                    ids["wren"],
                    "The mill is haunted",
                    ids["hearth"],
                    4,
                )
                assert claim.proposition == "the mill is haunted"
            async with create_unit_of_work(engine) as uow:
                wren = await uow.knowledge.get_belief(
                    ids["world"], ids["wren"], "the mill is haunted"
                )
                ash = await uow.knowledge.get_belief(
                    ids["world"], ids["ash"], "the mill is haunted"
                )
                bram = await uow.knowledge.get_belief(
                    ids["world"], ids["bram"], "the mill is haunted"
                )
                assert wren is not None and wren.confidence == 0.9
                assert ash is not None and ash.confidence == 0.5
                assert bram is None
            # Repetition reinforces toward the cap, never past it.
            async with create_unit_of_work(engine) as uow:
                for _ in range(5):
                    await assert_claim(
                        uow,
                        "watcher",
                        ids["world"],
                        ids["wren"],
                        "The mill is haunted",
                        ids["hearth"],
                        4,
                    )
            async with create_unit_of_work(engine) as uow:
                ash = await uow.knowledge.get_belief(
                    ids["world"], ids["ash"], "the mill is haunted"
                )
                assert ash is not None and ash.confidence == 0.9
        finally:
            await engine.dispose()

    _run(_inner())


def test_contradiction_halves_without_deleting(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_rooms()
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                first = await assert_claim(
                    uow,
                    "watcher",
                    ids["world"],
                    ids["wren"],
                    "The mill is haunted",
                    ids["hearth"],
                    4,
                )
            async with create_unit_of_work(engine) as uow:
                await assert_claim(
                    uow,
                    "watcher",
                    ids["world"],
                    ids["ash"],
                    "The mill is quiet",
                    ids["hearth"],
                    5,
                    refutes_claim_id=first.id,
                )
            async with create_unit_of_work(engine) as uow:
                ash_old = await uow.knowledge.get_belief(
                    ids["world"], ids["ash"], "the mill is haunted"
                )
                ash_new = await uow.knowledge.get_belief(
                    ids["world"], ids["ash"], "the mill is quiet"
                )
                wren_new = await uow.knowledge.get_belief(
                    ids["world"], ids["wren"], "the mill is quiet"
                )
                assert ash_old is not None and ash_old.confidence == 0.25
                assert ash_new is not None and ash_new.confidence == 0.9
                assert wren_new is not None and wren_new.confidence == 0.5
                # Sources survive: both claims and both beliefs persist.
                claims = await uow.knowledge.list_claims_for_world(ids["world"])
                assert len(claims) == 2
        finally:
            await engine.dispose()

    _run(_inner())


def test_false_claim_leaves_canon_untouched(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_rooms()
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                before_chars = await uow.characters.list_for_world(ids["world"])
                before_events = await uow.events.count_events(ids["world"])
            async with create_unit_of_work(engine) as uow:
                await assert_claim(
                    uow,
                    "watcher",
                    ids["world"],
                    ids["wren"],
                    "Ash stole the grain",
                    ids["hearth"],
                    4,
                )
            async with create_unit_of_work(engine) as uow:
                after_chars = await uow.characters.list_for_world(ids["world"])
                assert [c.model_dump() for c in after_chars] == [
                    c.model_dump() for c in before_chars
                ]
                assert await uow.events.count_events(ids["world"]) == before_events
                ash = await uow.knowledge.get_belief(
                    ids["world"], ids["ash"], "ash stole the grain"
                )
                assert ash is not None
        finally:
            await engine.dispose()

    _run(_inner())


def test_folding_math_is_pure() -> None:
    assert normalize("  The  Mill\tIs HAUNTED\n") == "the mill is haunted"
    assert reinforce(0.85) == 0.9
    assert reinforce(0.5) == 0.65
    assert contradict(0.5) == 0.25
    assert contradict(0.15) == 0.1


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


def test_claim_endpoints_filter_by_audience(client: ApiClient) -> None:
    headers = {"X-Worldsim-Role": "watcher"}
    ids = _run(_seed_rooms())
    voiced = client.post(
        "/api/v1/stage2/claims",
        json={
            "world_id": str(ids["world"]),
            "speaker_id": str(ids["wren"]),
            "proposition": "The mill is haunted",
            "audience_location_id": str(ids["hearth"]),
        },
        headers=headers,
    )
    assert voiced.status_code == 200, voiced.text
    ash_claims = client.get(
        "/api/v1/stage2/claims",
        params={"world_id": str(ids["world"]), "viewer_id": str(ids["ash"])},
        headers=headers,
    )
    assert len(ash_claims.json()["members"]) == 1
    bram_claims = client.get(
        "/api/v1/stage2/claims",
        params={"world_id": str(ids["world"]), "viewer_id": str(ids["bram"])},
        headers=headers,
    )
    assert bram_claims.json()["members"] == []
    ash_beliefs = client.get(
        "/api/v1/stage2/beliefs",
        params={"world_id": str(ids["world"]), "holder_id": str(ids["ash"])},
        headers=headers,
    )
    assert ash_beliefs.json()["members"][0]["confidence"] == 0.5
    # Non-watchers read only their own beliefs.
    player = {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(ids["bram"])}
    denied = client.get(
        "/api/v1/stage2/beliefs",
        params={"world_id": str(ids["world"]), "holder_id": str(ids["ash"])},
        headers=player,
    )
    assert denied.status_code == 403, denied.text
