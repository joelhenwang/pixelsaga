"""D&D narration wiring: party context, manifest sources, RECRUIT (owned by DND-WIRE)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.application.graphs.narrate import render_user_prompt
from worldsim.application.orchestration.service import derive_run_id
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.ids import (
    derive_combat_event_id,
    new_card_id,
    new_character_id,
    new_location_id,
    new_world_id,
)
from worldsim.domain.rules.dnd import load_data, resolve_narration_tags
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


@pytest.fixture
def wire(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


async def _seed_two() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            await uow.worlds.add(World(id=wid, name="Wire", seed_version="s1-test"))
            hearth, market = new_location_id(), new_location_id()
            await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth"))
            await uow.locations.add(Location(id=market, world_id=wid, name="Market"))
            wren, ash = new_character_id(), new_character_id()
            for cid, name, place in ((wren, "Wren", hearth), (ash, "Ash", market)):
                await uow.characters.add_identity(cid, wid, name)
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=cid, name=name, version=1)
                )
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
            await uow.versions.ensure(wid, wid, "world")
            await uow.commit()
            return {"world": wid, "wren": wren, "ash": ash}
    finally:
        await engine.dispose()


def test_user_prompt_carries_dnd_block() -> None:
    base = render_user_prompt(["a"], [{"key": "k", "value": "v"}], "e", None, 2)
    assert "D&D" not in base
    with_block = render_user_prompt(
        ["a"], [{"key": "k", "value": "v"}], "e", None, 2, dnd_context="D&D PARTY"
    )
    assert with_block.endswith("D&D PARTY")


def test_combat_tags_resolve_to_hp_events_and_beats(wire: tuple[ApiClient, FakeGateway]) -> None:
    import hashlib
    import random

    client, gateway = wire
    ids = asyncio.run(_seed_two())
    headers = {"X-Worldsim-Role": "watcher"}
    tables = load_data(ROOT / "content" / "dnd")

    begun = client.post(
        "/api/v1/stage1/party/begin",
        json={
            "world_id": str(ids["world"]),
            "name": "Borin",
            "race": "dwarf",
            "character_class": "fighter",
            "level": 1,
        },
        headers=headers,
    )
    assert begun.status_code == 200, begun.text

    snapshot = str(ids["world"])
    combat_text = (
        "Borin advances.\n"
        "ENCOUNTER[2x goblin]\n"
        "ATTACK[longsword at goblin]\n"
        "ATTACK[handaxe at goblin]\n"
        "CONDITION[poisoned on Borin for 2 rounds]"
    )

    def _route(request: Any) -> str | None:
        prompt, system = request.prompt, request.system or ""
        if "You narrate" in system:
            return json.dumps(
                [{"text": combat_text, "cited_fact_keys": ["attempt:wait", "dnd-sheet:borin"]}]
            )
        if "You resolve" in system:
            return json.dumps(
                {
                    "outcome": "success",
                    "effects": [
                        {
                            "schema_version": 1,
                            "affected_ids": [str(ids["wren"])],
                            "expected_versions": {str(ids["wren"]): 0},
                            "effect_type": "record_observation",
                            "observer_character_id": str(ids["wren"]),
                            "facts": [{"key": "greeting", "value": "dawn patrol"}],
                        }
                    ],
                    "rationale": "Wren hears the call.",
                }
            )
        if "You react" in system:
            if "Wren" in prompt:
                return json.dumps(
                    {
                        "family": "observe",
                        "character_id": str(ids["wren"]),
                        "snapshot_id": snapshot,
                        "focus": "Ash",
                    }
                )
            return json.dumps(
                {"family": "wait", "character_id": str(ids["ash"]), "snapshot_id": snapshot}
            )
        if "You decide" in system:
            who = ids["wren"] if "Wren" in prompt else ids["ash"]
            return json.dumps({"family": "wait", "character_id": str(who), "snapshot_id": snapshot})
        return None

    gateway.route = _route
    response = client.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(ids["world"]), "absolute_index": 1},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    scene_event = UUID(response.json()["scenes"][0]["event_id"])

    async def _roster_sheets() -> dict[str, Any]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                return {
                    m.name_key: m.sheet.model_dump()
                    for m in await uow.party.list_for_world(ids["world"])
                }
        finally:
            await engine.dispose()

    # Recompute the expected report from the pre-combat sheets and seed.
    from worldsim.domain.rules.dnd import Sheet as SheetModel

    before = asyncio.run(_roster_sheets())
    seed = int.from_bytes(hashlib.sha256(str(scene_event).encode()).digest()[:8], "big") & (
        (1 << 63) - 1
    )
    expected = resolve_narration_tags(
        combat_text,
        [SheetModel.model_validate(before["borin"])],
        tables,
        random.Random(seed).random,
    )
    after = asyncio.run(_roster_sheets())
    assert after["borin"]["hp"]["current"] == before["borin"]["hp"]["current"]
    assert after["borin"]["conditions"] == ["Poisoned"]

    async def _combat_records() -> dict[str, Any]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                combat_id = derive_combat_event_id(scene_event)
                event = await uow.events.get_event(combat_id)
                beats = await uow.scenes.narrations_for_event(combat_id)
                return {
                    "type": event.event_type.value,
                    "seed": event.random_seed,
                    "algorithm": event.random_algorithm,
                    "beats": [b.text for b in beats],
                    "cited": [list(b.cited_fact_keys) for b in beats],
                }
        finally:
            await engine.dispose()

    records = asyncio.run(_combat_records())
    assert records["type"] == "action_resolved"
    assert records["seed"] == seed
    assert records["algorithm"] == "seeded-d20-v1"
    assert records["beats"] == [b.text for b in expected.beats]
    assert all("dnd-sheet:borin" in cited for cited in records["cited"])

    roster = client.get(
        "/api/v1/stage1/party", params={"world_id": str(ids["world"])}, headers=headers
    )
    assert roster.status_code == 200, roster.text
    borin = roster.json()["members"][0]
    assert borin["conditions"] == ["Poisoned"]
    assert borin["hp_current"] == after["borin"]["hp"]["current"]


def test_party_context_and_recruit_flow(wire: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = wire
    ids = asyncio.run(_seed_two())
    headers = {"X-Worldsim-Role": "watcher"}

    begun = client.post(
        "/api/v1/stage1/party/begin",
        json={
            "world_id": str(ids["world"]),
            "name": "Borin",
            "race": "dwarf",
            "character_class": "fighter",
            "level": 1,
        },
        headers=headers,
    )
    assert begun.status_code == 200, begun.text
    roster = client.get(
        "/api/v1/stage1/party", params={"world_id": str(ids["world"])}, headers=headers
    )
    assert [m["name"] for m in roster.json()["members"]] == ["Borin"]
    borin = roster.json()["members"][0]
    assert borin["level"] == 1 and borin["character_class"] == "fighter"
    assert isinstance(borin["hp_current"], int) and borin["hp_current"] == borin["hp_max"]
    assert borin["conditions"] == []

    snapshot = str(ids["world"])
    narrator_text = "The phase passes.\nRECRUIT[Lyra]: elf ranger, level 3"

    def _route(request: Any) -> str | None:
        prompt, system = request.prompt, request.system or ""
        if "You narrate" in system:
            assert "D&D PARTY" in prompt and "D&D MODE" in prompt
            return json.dumps(
                [{"text": narrator_text, "cited_fact_keys": ["attempt:wait", "dnd-sheet:borin"]}]
            )
        if "You resolve" in system:
            return json.dumps(
                {
                    "outcome": "success",
                    "effects": [
                        {
                            "schema_version": 1,
                            "affected_ids": [str(ids["wren"])],
                            "expected_versions": {str(ids["wren"]): 0},
                            "effect_type": "record_observation",
                            "observer_character_id": str(ids["wren"]),
                            "facts": [{"key": "greeting", "value": "dawn patrol"}],
                        }
                    ],
                    "rationale": "Wren hears the call.",
                }
            )
        if "You react" in system:
            if "Wren" in prompt:
                return json.dumps(
                    {
                        "family": "observe",
                        "character_id": str(ids["wren"]),
                        "snapshot_id": snapshot,
                        "focus": "Ash",
                    }
                )
            return json.dumps(
                {"family": "wait", "character_id": str(ids["ash"]), "snapshot_id": snapshot}
            )
        if "You decide" in system:
            who = ids["wren"] if "Wren" in prompt else ids["ash"]
            return json.dumps({"family": "wait", "character_id": str(who), "snapshot_id": snapshot})
        return None

    gateway.route = _route
    response = client.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(ids["world"]), "absolute_index": 1},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    # The narration scan seated Lyra; the manifest cites Borin's sheet.
    roster = client.get(
        "/api/v1/stage1/party", params={"world_id": str(ids["world"])}, headers=headers
    )
    assert [m["name"] for m in roster.json()["members"]] == ["Borin", "Lyra"]

    async def _manifest_kinds() -> set[str]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                run_id = derive_run_id(ids["world"], 1)
                kinds: set[str] = set()
                for call in await uow.traces.list_for_phase_run(run_id):
                    if call.role != "narrator":
                        continue
                    manifest = await uow.traces.get_manifest(call.id)
                    kinds.update(source.kind for source in manifest.sources)
                return kinds
        finally:
            await engine.dispose()

    assert "dnd-sheet" in asyncio.run(_manifest_kinds())

    # Replay is stable: no duplicate Lyra, no new model work.
    again = client.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(ids["world"]), "absolute_index": 1},
        headers=headers,
    )
    assert again.json()["duplicate"] is True
    roster = client.get(
        "/api/v1/stage1/party", params={"world_id": str(ids["world"])}, headers=headers
    )
    assert len(roster.json()["members"]) == 2
