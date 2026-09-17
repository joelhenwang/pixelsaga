"""Inventory ownership and training progress (owned by S2-PROGRESS-001)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.application.commands.inventory import give_item, transfer_item
from worldsim.domain.characters import Character
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_character_id, new_location_id, new_world_id
from worldsim.domain.items import load_item_definitions
from worldsim.domain.progress import fold_progress, session_gain
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
CATALOG = load_item_definitions(ROOT / "content" / "definitions" / "items.json")


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


async def _seed_holder(stamina: int = 80) -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            home = new_location_id()
            cid = new_character_id()
            await uow.worlds.add(World(id=wid, name="Vale", seed_version="s2-test"))
            await uow.locations.add(Location(id=home, world_id=wid, name="Hearth", capacity=4))
            await uow.characters.add_identity(cid, wid, "Wren")
            await uow.characters.add_state(
                Character(
                    id=cid,
                    world_id=wid,
                    name="Wren",
                    card_version=1,
                    location_id=home,
                    stamina=stamina,
                    mana=40,
                )
            )
            await uow.versions.ensure(cid, wid, "character")
            await uow.commit()
            return {"world": wid, "home": home, "wren": cid}
    finally:
        await engine.dispose()


def test_single_owner_transfer_guards(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_holder()
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                with pytest.raises(DomainError) as exc_info:
                    await give_item(uow, "watcher", ids["world"], "vorpal", ids["wren"], CATALOG)
                assert exc_info.value.code == ErrorCode.NOT_FOUND
                torch = await give_item(
                    uow,
                    "watcher",
                    ids["world"],
                    "torch",
                    ids["wren"],
                    CATALOG,
                    quantity=2,
                )
                assert torch.owner_id == ids["wren"] and torch.quantity == 2
            async with create_unit_of_work(engine) as uow:
                same = await transfer_item(uow, "watcher", torch.id, ids["wren"])
                assert same.version == torch.version
                dropped = await transfer_item(uow, "watcher", torch.id, None)
                assert dropped.owner_id is None
            async with create_unit_of_work(engine) as uow:
                ground = await uow.inventory.list_for_owner(ids["world"], None)
                assert [i.item_key for i in ground] == ["torch"]
                held = await uow.inventory.list_for_owner(ids["world"], ids["wren"])
                assert held == []
        finally:
            await engine.dispose()

    _run(_inner())


def test_resolver_cannot_award_progress() -> None:
    from worldsim.domain.enums import EffectType
    from worldsim.domain.rules.resolution import STAGE1_FEASIBLE_EFFECTS

    assert EffectType.SKILL_PROGRESS not in STAGE1_FEASIBLE_EFFECTS


def test_gain_math_is_pure() -> None:
    assert [session_gain(n) for n in range(10)] == [8, 7, 6, 5, 4, 3, 2, 1, 1, 1]
    assert fold_progress(95, 8) == 100
    assert fold_progress(10, 5) == 15


def test_catalog_rejects_duplicates_and_unknowns(tmp_path: Any) -> None:
    import json

    assert set(CATALOG) >= {"torch", "ration", "rope", "herb", "longsword", "handaxe"}
    assert CATALOG["torch"].stackable is True
    dupes = tmp_path / "items.json"
    dupes.write_text(
        json.dumps(
            {
                "items": [
                    {"key": "torch", "name": "Torch"},
                    {"key": "torch", "name": "Torch again"},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate item key"):
        load_item_definitions(dupes)


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


def test_training_awards_once_through_tick(client: ApiClient) -> None:
    headers = {"X-Worldsim-Role": "watcher"}
    ids = _run(_seed_holder())
    started = client.post(
        "/api/v1/stage2/activities",
        json={
            "world_id": str(ids["world"]),
            "character_id": str(ids["wren"]),
            "kind": "train",
            "duration_phases": 1,
            "skill": "swords",
        },
        headers=headers,
    )
    assert started.status_code == 200, started.text
    first = client.post(
        "/api/v1/stage2/activities",
        json={
            "world_id": str(ids["world"]),
            "character_id": str(ids["wren"]),
            "kind": "work",
            "duration_phases": 1,
        },
        headers=headers,
    )
    assert first.status_code == 409, first.text


def test_same_session_counts_once(migrated_db: None) -> None:
    from uuid import uuid4

    from worldsim.application.transactions.canonical import (
        CanonicalTransaction,
        CommitRequest,
        canonical_input_hash,
    )
    from worldsim.domain.effects import SkillProgressEffect
    from worldsim.domain.enums import EventType
    from worldsim.domain.phases import PhaseRun

    async def _inner() -> None:
        ids = await _seed_holder()
        engine = create_engine(Settings())
        factory = lambda: create_unit_of_work(engine)  # noqa: E731
        canonical = CanonicalTransaction(factory)
        try:
            async with create_unit_of_work(engine) as uow:
                run_id = uuid4()
                await uow.phases.create_run(
                    PhaseRun(id=run_id, world_id=ids["world"], absolute_index=1)
                )
                await uow.commit()

            async def _commit(key: str, version: int) -> None:
                effect = SkillProgressEffect(
                    affected_ids=[ids["wren"]],
                    expected_versions={str(ids["wren"]): version},
                    character_id=ids["wren"],
                    skill_key="swords",
                    session_key="drill-at-dawn",
                )
                await canonical.commit(
                    CommitRequest(
                        command_id=uuid4(),
                        world_id=ids["world"],
                        idempotency_key=key,
                        actor_role="system",
                        command_type="record_training",
                        expected_versions={str(ids["wren"]): version},
                        payload={"skill": "swords"},
                        input_hash=canonical_input_hash({"key": key}),
                        absolute_index=1,
                        phase_run_id=run_id,
                        event_type=EventType.ACTION_RESOLVED,
                        effects=[effect],
                    )
                )

            await _commit("train:one", 0)
            # No state changed, so the observed version is still 0; the
            # store only advances for persisted rows (compare-all,
            # bump-saved).
            await _commit("train:two", 0)
            async with create_unit_of_work(engine) as uow:
                skill = await uow.progress.get_skill(ids["world"], ids["wren"], "swords")
                assert skill is not None
                assert (skill.progress, skill.sessions) == (8, 1)
        finally:
            await engine.dispose()

    _run(_inner())


def test_item_endpoints_move_single_owner(client: ApiClient) -> None:
    headers = {"X-Worldsim-Role": "watcher"}
    ids = _run(_seed_holder())
    given = client.post(
        "/api/v1/stage2/items/give",
        json={"world_id": str(ids["world"]), "item_key": "rope", "owner_id": str(ids["wren"])},
        headers=headers,
    )
    assert given.status_code == 200, given.text
    item_id = given.json()["id"]
    moved = client.post(
        f"/api/v1/stage2/items/{item_id}/transfer",
        json={"to_owner_id": None},
        headers=headers,
    )
    assert moved.json()["owner_id"] is None
    skills = client.get(
        "/api/v1/stage2/skills",
        params={"world_id": str(ids["world"]), "character_id": str(ids["wren"])},
        headers=headers,
    )
    assert skills.json()["members"] == []
