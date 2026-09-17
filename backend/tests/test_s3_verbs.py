"""Stage 3 v2 verb tests (owned by S3-RULE-001).

Spar, appeal, and transfer intents through the HTTP boundary:
validator rejections, seeded determinism, settle persistence,
and replay idempotency.

Bout sheets resolve by roster name: the D&D roster holds sheets
while characters act, so spar needs begun members sharing the
combatants' names. Missing sheets fail loud at settle.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.domain.commands import AppealAction, SparAction, TransferAction
from worldsim.domain.enums import LifeStatus
from worldsim.domain.errors import DomainError
from worldsim.domain.rules.actions import check_appeal, check_spar, check_transfer
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"

WORLD_ID = UUID("10000000-0000-4000-8000-000000000001")
WREN_ID = UUID("10000000-0000-4000-8000-000000000101")
ASH_ID = UUID("10000000-0000-4000-8000-000000000102")
HEARTH_ID = UUID("10000000-0000-4000-8000-000000000011")
MARKET_ID = UUID("10000000-0000-4000-8000-000000000012")
PLACEHOLDER_SNAPSHOT = "00000000-0000-4000-8000-000000000000"


@pytest.fixture
def verbs(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def _wait_json(actor: UUID) -> str:
    return json.dumps(
        {"family": "wait", "character_id": str(actor), "snapshot_id": PLACEHOLDER_SNAPSHOT}
    )


def _spar_view() -> Any:
    from worldsim.domain.characters import Character
    from worldsim.domain.rules.views import WorldView
    from worldsim.domain.world import Location, World

    wid = uuid4()
    hearth = Location(id=uuid4(), world_id=wid, name="Hearth")
    market = Location(id=uuid4(), world_id=wid, name="Market")
    wren = Character(
        id=uuid4(),
        world_id=wid,
        name="Wren",
        card_version=1,
        location_id=hearth.id,
        stamina=80,
        mana=40,
    )
    ash = Character(
        id=uuid4(),
        world_id=wid,
        name="Ash",
        card_version=1,
        location_id=market.id,
        stamina=80,
        mana=40,
    )
    return (
        WorldView(
            world=World(id=wid, name="Vale", seed_version="test"),
            characters=[wren, ash],
            locations=[hearth, market],
        ),
        wren,
        ash,
    )


def _action_json(action: str, actor: UUID, **fields: object) -> str:
    return json.dumps(
        {
            "family": action,
            "character_id": str(actor),
            "snapshot_id": PLACEHOLDER_SNAPSHOT,
            **{k: str(v) for k, v in fields.items()},
        }
    )


def test_check_spar_rejects_self_remote_and_dead() -> None:
    view, wren, ash = _spar_view()
    with pytest.raises(DomainError):
        check_spar(
            wren,
            SparAction(character_id=wren.id, snapshot_id=uuid4(), target_character_id=wren.id),
            view,
        )
    with pytest.raises(DomainError):
        check_spar(
            wren,
            SparAction(character_id=wren.id, snapshot_id=uuid4(), target_character_id=ash.id),
            view,
        )
    dead = wren.model_copy(update={"life_status": LifeStatus.DEAD})
    with pytest.raises(DomainError):
        check_spar(
            dead,
            SparAction(character_id=wren.id, snapshot_id=uuid4(), target_character_id=ash.id),
            view,
        )


def test_check_appeal_and_transfer_reject() -> None:
    view, wren, ash = _spar_view()
    check_appeal(
        wren,
        AppealAction(character_id=wren.id, snapshot_id=uuid4(), proposition="The mill stands"),
        view,
    )
    with pytest.raises(DomainError):
        check_transfer(
            wren,
            TransferAction(
                character_id=wren.id,
                snapshot_id=uuid4(),
                item_instance_id=uuid4(),
                target_character_id=wren.id,
            ),
            view,
        )
    with pytest.raises(DomainError):
        check_transfer(
            wren,
            TransferAction(
                character_id=wren.id,
                snapshot_id=uuid4(),
                item_instance_id=uuid4(),
                target_character_id=ash.id,
            ),
            view,
        )


def _setup_world(client: ApiClient, headers: dict[str, str], verbs: dict[str, str]) -> None:
    assert client.post("/api/v1/world/seed", headers=headers).status_code == 200
    for name in ("Wren", "Ash"):
        begun = client.post(
            "/api/v1/stage1/party/begin",
            json={
                "world_id": str(WORLD_ID),
                "name": name,
                "race": "human",
                "character_class": "fighter",
                "level": 3,
            },
            headers=headers,
        )
        assert begun.status_code == 200, begun.text

    async def _gather() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                wren = await uow.characters.get(WREN_ID)
                await uow.characters.save_state(
                    wren.model_copy(update={"location_id": MARKET_ID}), wren.version
                )
                await uow.versions.compare_and_bump({WREN_ID: wren.version})
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(_gather())
    _verbs_state.update(verbs)


_verbs_state: dict[str, str] = {}


def _route_for() -> Any:
    def _route(request: Any) -> str | None:
        prompt, system = request.prompt, request.system or ""
        if "You decide" in system:
            if "Wren" in prompt and "wren" in _verbs_state:
                kind = _verbs_state["wren"]
                if kind == "spar":
                    return _action_json("spar", WREN_ID, target_character_id=ASH_ID)
                if kind == "appeal":
                    return _action_json(
                        "appeal",
                        WREN_ID,
                        proposition="The mill is haunted",
                        audience_location_id=MARKET_ID,
                    )
                if kind == "give":
                    return _action_json(
                        "transfer",
                        WREN_ID,
                        item_instance_id=_verbs_state["item"],
                        target_character_id=ASH_ID,
                    )
            return _wait_json(WREN_ID if "Wren" in prompt else ASH_ID)
        if "You react" in system:
            return _wait_json(WREN_ID if "Wren" in prompt else ASH_ID)
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Verb."})
        if "You narrate" in system:
            return json.dumps(
                [{"text": "They train together.", "cited_fact_keys": ["attempt:wait"]}]
            )
        if "You direct" in system:
            return json.dumps({"action": "noop", "reason": "calm"})
        if "You summar" in system or "You distill" in system:
            return json.dumps({"text": "A quiet day.", "source_ids": []})
        return None

    return _route


def _audit_spar() -> dict[str, Any]:
    async def _audit() -> dict[str, Any]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                roster = await uow.party.list_for_world(WORLD_ID)
                by_name = {m.name: m for m in roster}
                assert by_name["Ash"].sheet.hp is not None
                events = await uow.events.list_range(WORLD_ID, after=0, limit=1000)
                combats = [
                    e
                    for e in events
                    if e.event_type.value == "action_resolved" and e.random_seed is not None
                ]
                return {
                    "ash_hp": by_name["Ash"].sheet.hp.current,
                    "ash_max": by_name["Ash"].sheet.hp.max,
                    "combats": len(combats),
                    "log": combats[0].random_result if combats else None,
                }
        finally:
            await engine.dispose()

    return asyncio.run(_audit())


def test_spar_bout_persists_and_replays_clean(
    verbs: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = verbs
    gateway.route = _route_for()
    headers = {"X-Worldsim-Role": "watcher"}
    _setup_world(client, headers, {"wren": "spar"})
    first = client.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(WORLD_ID), "absolute_index": 1},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    findings = _audit_spar()
    assert findings["combats"] == 1
    assert findings["log"] is not None
    if "hits" in findings["log"]:
        assert findings["ash_hp"] < findings["ash_max"]
    else:
        assert "misses" in findings["log"]
        assert findings["ash_hp"] == findings["ash_max"]

    replay = client.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(WORLD_ID), "absolute_index": 1},
        headers=headers,
    )
    assert replay.json()["duplicate"] is True
    assert _audit_spar() == findings


def test_summarize_falls_back_to_author_on_mismatch() -> None:
    from uuid import uuid4

    from worldsim.application.orchestration.stage1 import _summarize
    from worldsim.domain.commands import WaitAction

    wren, ash = uuid4(), uuid4()
    names = {wren: "Wren", ash: "Ash"}
    assert _summarize(WaitAction(character_id=wren, snapshot_id=uuid4()), names) == "Wren waits"
    assert (
        _summarize(WaitAction(character_id=uuid4(), snapshot_id=uuid4()), names, wren)
        == "Wren waits"
    )


def test_touch_without_save_never_desyncs(verbs: tuple[ApiClient, FakeGateway]) -> None:
    """Communicate touches aggregates without state saves; a later
    touching commit must not 409. Regression for the version-store
    drift that compare-and-bump-everything introduced."""
    client, gateway = verbs
    gateway.route = _route_for()
    headers = {"X-Worldsim-Role": "watcher"}
    _setup_world(client, headers, {})
    for index, family in (
        (
            1,
            {
                "family": "communicate",
                "character_id": str(WREN_ID),
                "snapshot_id": PLACEHOLDER_SNAPSHOT,
                "target_character_id": str(ASH_ID),
                "topic": "probe",
            },
        ),
        (
            2,
            {
                "family": "appeal",
                "character_id": str(WREN_ID),
                "snapshot_id": PLACEHOLDER_SNAPSHOT,
                "proposition": "the mill stands",
            },
        ),
    ):
        response = client.post(
            "/api/v1/stage1/advance",
            json={
                "world_id": str(WORLD_ID),
                "absolute_index": index,
                "player_intents": {str(WREN_ID): family},
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
    beliefs = client.get(
        "/api/v1/stage2/beliefs",
        params={"world_id": str(WORLD_ID), "holder_id": str(WREN_ID)},
        headers=headers,
    )
    assert any(b["proposition"] == "the mill stands" for b in beliefs.json()["members"])


def test_appeal_files_positional_claim(verbs: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = verbs
    gateway.route = _route_for()
    headers = {"X-Worldsim-Role": "watcher"}
    _setup_world(client, headers, {"wren": "appeal"})
    response = client.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(WORLD_ID), "absolute_index": 1},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    wren_beliefs = client.get(
        "/api/v1/stage2/beliefs",
        params={"world_id": str(WORLD_ID), "holder_id": str(WREN_ID)},
        headers=headers,
    )
    ash_beliefs = client.get(
        "/api/v1/stage2/beliefs",
        params={"world_id": str(WORLD_ID), "holder_id": str(ASH_ID)},
        headers=headers,
    )
    assert any(b["proposition"] == "the mill is haunted" for b in wren_beliefs.json()["members"])
    assert any(b["proposition"] == "the mill is haunted" for b in ash_beliefs.json()["members"])
    claims = client.get(
        "/api/v1/stage2/claims",
        params={"world_id": str(WORLD_ID), "viewer_id": str(WREN_ID)},
        headers=headers,
    )
    assert any(c["proposition"] == "the mill is haunted" for c in claims.json()["members"])


def test_give_hands_item_to_recipient(verbs: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = verbs
    gateway.route = _route_for()
    headers = {"X-Worldsim-Role": "watcher"}
    _setup_world(client, headers, {"wren": "give"})
    given = client.post(
        "/api/v1/stage2/items/give",
        json={"world_id": str(WORLD_ID), "item_key": "rope", "owner_id": str(WREN_ID)},
        headers=headers,
    )
    assert given.status_code == 200, given.text
    _verbs_state["item"] = given.json()["id"]
    response = client.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(WORLD_ID), "absolute_index": 1},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    async def _owner() -> str | None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                from uuid import UUID as Uuid

                item = await uow.inventory.get_item(Uuid(given.json()["id"]))
                return str(item.owner_id) if item.owner_id else None
        finally:
            await engine.dispose()

    assert asyncio.run(_owner()) == str(ASH_ID)
