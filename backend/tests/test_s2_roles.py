"""Role grants, Director proposals, and deity overrides (owned by S2-ROLE-001)."""

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
from worldsim.domain.phases import PhaseRun
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
            from worldsim.domain.ids import new_phase_run_id

            wid = new_world_id()
            home = new_location_id()
            wren = new_character_id()
            await uow.worlds.add(World(id=wid, name="Vale", seed_version="s2-test"))
            await uow.locations.add(Location(id=home, world_id=wid, name="Hearth", capacity=4))
            await uow.characters.add_identity(wren, wid, "Wren")
            await uow.characters.add_state(
                Character(
                    id=wren,
                    world_id=wid,
                    name="Wren",
                    card_version=1,
                    location_id=home,
                    stamina=80,
                    mana=40,
                )
            )
            await uow.versions.ensure(wren, wid, "character")
            await uow.phases.create_run(
                PhaseRun(id=new_phase_run_id(), world_id=wid, absolute_index=1)
            )
            await uow.commit()
            return {"world": wid, "wren": wren, "home": home}
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


def test_role_select_enforces_boundary_and_binding(client: ApiClient) -> None:
    headers = {"X-Worldsim-Role": "watcher"}
    ids = _run(_seed_realm())
    denied = client.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(ids["world"]), "role": "player"},
        headers=headers,
    )
    assert denied.status_code == 422, denied.text
    selected = client.post(
        "/api/v1/stage2/roles/select",
        json={
            "world_id": str(ids["world"]),
            "role": "player",
            "character_id": str(ids["wren"]),
        },
        headers=headers,
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["role"] == "player"
    current = client.get(
        "/api/v1/stage2/roles",
        params={"world_id": str(ids["world"])},
        headers=headers,
    )
    assert current.json()["character_id"] == str(ids["wren"])

    async def _start_run() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                from worldsim.domain.enums import PhaseRunState

                run = await uow.phases.find_open_run(ids["world"])
                assert run is not None
                await uow.phases.set_run_state(run.id, PhaseRunState.WORLD_TICKED.value)
                await uow.commit()
        finally:
            await engine.dispose()

    _run(_start_run())
    mid_run = client.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(ids["world"]), "role": "watcher"},
        headers=headers,
    )
    assert mid_run.status_code == 409, mid_run.text


def test_director_proposal_accept_and_reject(client: ApiClient) -> None:
    watcher = {"X-Worldsim-Role": "watcher"}
    ids = _run(_seed_realm())
    granted = client.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(ids["world"]), "role": "director"},
        headers=watcher,
    )
    assert granted.status_code == 200, granted.text
    director = {"X-Worldsim-Role": "director"}
    accepted = client.post(
        "/api/v1/stage2/director/proposals",
        json={
            "world_id": str(ids["world"]),
            "kind": "hook",
            "title": "A peddler arrives",
            "purpose": "Trade news.",
            "requested_powers": [],
            "participant_ids": [str(ids["wren"])],
        },
        headers=director,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["title"] == "A peddler arrives"
    rejected = client.post(
        "/api/v1/stage2/director/proposals",
        json={
            "world_id": str(ids["world"]),
            "kind": "hook",
            "title": "A shadow falls",
            "requested_powers": ["kill_character"],
        },
        headers=director,
    )
    assert rejected.status_code == 422, rejected.text
    fresh = _run(_seed_realm())
    player = {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(fresh["wren"])}
    forbidden = client.post(
        "/api/v1/stage2/director/proposals",
        json={"world_id": str(fresh["world"]), "kind": "hook", "title": "Sneaky"},
        headers=player,
    )
    assert forbidden.status_code == 403, forbidden.text


def test_deity_override_applies_with_audit(client: ApiClient) -> None:
    watcher = {"X-Worldsim-Role": "watcher"}
    ids = _run(_seed_realm())
    granted = client.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(ids["world"]), "role": "deity"},
        headers=watcher,
    )
    assert granted.status_code == 200, granted.text
    deity = {"X-Worldsim-Role": "deity"}
    applied = client.post(
        "/api/v1/stage2/deity/overrides",
        json={
            "world_id": str(ids["world"]),
            "character_id": str(ids["wren"]),
            "stamina": 10,
            "retcon": True,
        },
        headers=deity,
    )
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["retcon"] is True
    engine = create_engine(Settings())
    try:

        async def _check() -> None:
            async with create_unit_of_work(engine) as uow:
                wren = await uow.characters.get(ids["wren"])
                assert wren.stamina == 10
                event = await uow.events.get_event(UUID(body["event_id"]))
                assert event.event_type == "deity_override"
                from worldsim.domain.effects import DeityOverrideEffect

                stored = await uow.events.list_effects(event.id)
                assert isinstance(stored[0].effect, DeityOverrideEffect)
                assert stored[0].effect.retcon is True
                messages = await uow.outbox.claim_due(10)
                assert any(m.kind == "consistency_audit" for m in messages)

        _run(_check())
    finally:
        asyncio.run(engine.dispose())
    fresh = _run(_seed_realm())
    denied = client.post(
        "/api/v1/stage2/deity/overrides",
        json={"world_id": str(fresh["world"]), "character_id": str(fresh["wren"]), "stamina": 10},
        headers=watcher,
    )
    assert denied.status_code == 403, denied.text


def test_grant_governs_all_callers(client: ApiClient) -> None:
    watcher = {"X-Worldsim-Role": "watcher"}
    ids = _run(_seed_realm())
    client.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(ids["world"]), "role": "deity"},
        headers=watcher,
    )
    # The active grant governs every caller: a player header neither
    # escalates nor restricts while deity is selected.
    player = {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(ids["wren"])}
    applied = client.post(
        "/api/v1/stage2/deity/overrides",
        json={"world_id": str(ids["world"]), "character_id": str(ids["wren"]), "stamina": 10},
        headers=player,
    )
    assert applied.status_code == 200, applied.text
