"""Stage 5 interleave test: detailed to macro to detailed through HTTP.

Ten detailed phases, a macro day carrying a birth, a communicate
intent to the newborn on the first resumed detailed phase (the exact
touch that 409s when the version store drifts), nine more detailed
phases, and a second macro day. Proves clock continuity, the
macro-coverage exemption, and row/store lockstep across the seam.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from test_stage1_api import ApiClient

from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.ids import (
    derive_lineage_child_id,
    new_card_id,
    new_character_id,
    new_location_id,
    new_schedule_id,
    new_world_id,
)
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

ZERO = "00000000-0000-4000-8000-000000000000"


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def _watcher() -> dict[str, str]:
    return {"X-Worldsim-Role": "watcher"}


def _advance(
    client: ApiClient, world: UUID, index: int, player_intents: dict[str, Any] | None = None
) -> httpx.Response:
    body: dict[str, Any] = {"world_id": str(world), "absolute_index": index}
    if player_intents:
        body["player_intents"] = player_intents
    return client.post("/api/v1/stage1/advance", json=body, headers=_watcher())


async def _seed_two() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            await uow.worlds.add(World(id=wid, name="Api", seed_version="s1-test"))
            hearth, market = new_location_id(), new_location_id()
            await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth"))
            await uow.locations.add(Location(id=market, world_id=wid, name="Market"))
            wren, ash = new_character_id(), new_character_id()
            for cid, name, place in ((wren, "Wren", hearth), (ash, "Ash", market)):
                await uow.characters.add_identity(cid, wid, name)
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=cid, name=name)
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


def test_detailed_macro_detailed_continuity(migrated_db: None) -> None:
    from fastapi.testclient import TestClient

    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        client = ApiClient(raw)
        _run(_inner(client, gateway))


async def _inner(client: ApiClient, gateway: FakeGateway) -> None:
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    ids = await _seed_two()
    wid, wren = ids["world"], ids["wren"]

    birth_schedule = new_schedule_id()
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            await uow.schedules.add(
                ScheduledEffect(
                    id=birth_schedule,
                    world_id=wid,
                    due_absolute=12,
                    kind="birth",
                    payload={"name": "Cora", "parent_ids": [str(wren)]},
                )
            )
            await uow.commit()
    finally:
        await engine.dispose()

    def _wait(actor: UUID) -> str:
        return json.dumps({"family": "wait", "character_id": str(actor), "snapshot_id": ZERO})

    def _route(request: Any) -> Any:
        prompt, system = request.prompt, request.system or ""
        match = re.search(r">>(Wren|Ash)\.", prompt)
        actor = ids["wren"] if match and match.group(1) == "Wren" else ids["ash"]
        if "You decide" in system or "You react" in system:
            return _wait(actor)
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "ok"})
        if "You narrate" in system:
            return json.dumps([{"text": "Calm.", "cited_fact_keys": ["attempt:wait"]}])
        if "You direct" in system:
            return json.dumps({"action": "noop", "reason": "calm"})
        if "You summar" in system or "You distill" in system:
            return json.dumps({"text": "Quiet.", "source_ids": []})
        return None

    gateway.route = _route
    headers = _watcher()
    for index in range(1, 11):
        report = _advance(client, wid, index)
        assert report.status_code == 200, (index, report.text)

    macro = client.post(
        "/api/v1/macro/advance",
        json={"world_id": str(wid), "day": 2, "resolution": "day"},
        headers=headers,
    )
    assert macro.status_code == 200, macro.text
    assert macro.json()["state"] == "completed"

    cora = derive_lineage_child_id(birth_schedule)
    snapshot = derive_snapshot_id(derive_run_id(wid, 20))
    talk = {
        str(wren): {
            "family": "communicate",
            "character_id": str(wren),
            "snapshot_id": str(snapshot),
            "target_character_id": str(cora),
            "topic": "welcome",
        }
    }
    resumed = _advance(client, wid, 20, talk)
    assert resumed.status_code == 200, resumed.text
    for index in range(21, 31):
        report = _advance(client, wid, index)
        assert report.status_code == 200, (index, report.text)
        clock = client.get("/api/v1/world/clock", headers=headers).json()
        assert clock["absolute_index"] == index, (index, clock)

    macro2 = client.post(
        "/api/v1/macro/advance",
        json={"world_id": str(wid), "day": 4, "resolution": "day"},
        headers=headers,
    )
    assert macro2.status_code == 200, macro2.text

    timeline = client.get(
        "/api/v1/stage2/timeline",
        params={"world_id": str(wid), "after": 0, "limit": 100},
        headers=headers,
    )
    assert timeline.status_code == 200
    types = {e["event_type"] for e in timeline.json()["entries"]}
    assert {"world_ticked", "macro_ticked", "schedule_fired"} <= types

    lineage = client.get("/api/v1/macro/lineage", params={"world_id": str(wid)}, headers=headers)
    assert lineage.status_code == 200
    names = {r["name"] for r in lineage.json()["records"]}
    assert "Cora" in names
