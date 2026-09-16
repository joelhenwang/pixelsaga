"""Directional relationships: evidence, folding, reads, context (owned by S2-REL-001)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.application.commands.relationships import record_evidence
from worldsim.domain.characters import Character
from worldsim.domain.enums import RelationshipDimension
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_character_id, new_location_id, new_world_id
from worldsim.domain.relationships import describe
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


async def _seed_pair() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            wren = new_character_id()
            ash = new_character_id()
            await uow.worlds.add(World(id=wid, name="Vale", seed_version="s2-test"))
            hearth = new_location_id()
            await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth", capacity=4))
            for cid, name in ((wren, "Wren"), (ash, "Ash")):
                await uow.characters.add_identity(cid, wid, name)
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=wid,
                        name=name,
                        card_version=1,
                        location_id=hearth,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
            await uow.commit()
            return {"world": wid, "wren": wren, "ash": ash}
    finally:
        await engine.dispose()


def test_directions_fold_independently(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_pair()
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                forth = await record_evidence(
                    uow,
                    "watcher",
                    ids["world"],
                    ids["wren"],
                    ids["ash"],
                    RelationshipDimension.TRUST,
                    5,
                    "kept watch",
                )
                assert (forth.trust, forth.affection) == (5, 0)
                back = await record_evidence(
                    uow,
                    "watcher",
                    ids["world"],
                    ids["ash"],
                    ids["wren"],
                    RelationshipDimension.TRUST,
                    -3,
                    "broke cover",
                )
                assert back.trust == -3
            async with create_unit_of_work(engine) as uow:
                wren_view = await uow.relationships.list_for_character(ids["world"], ids["wren"])
                assert len(wren_view) == 2
                assert forth.version == 1
                repeat = await record_evidence(
                    uow,
                    "watcher",
                    ids["world"],
                    ids["wren"],
                    ids["ash"],
                    RelationshipDimension.TRUST,
                    5,
                    "kept watch",
                )
                assert repeat.trust == 10
        finally:
            await engine.dispose()

    _run(_inner())


def test_evidence_validation(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_pair()
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                with pytest.raises(DomainError) as exc_info:
                    await record_evidence(
                        uow,
                        "watcher",
                        ids["world"],
                        ids["wren"],
                        ids["wren"],
                        RelationshipDimension.TRUST,
                        1,
                    )
                assert exc_info.value.code == ErrorCode.VALIDATION_FAILED
                with pytest.raises(DomainError) as exc_info:
                    await record_evidence(
                        uow,
                        "watcher",
                        ids["world"],
                        ids["wren"],
                        new_character_id(),
                        RelationshipDimension.TRUST,
                        1,
                    )
                assert exc_info.value.code == ErrorCode.NOT_FOUND
        finally:
            await engine.dispose()

    _run(_inner())


def test_clamp_and_describe() -> None:
    from worldsim.domain.relationships import Relationship

    assert "trust 12" in describe(
        Relationship(
            id="00000000-0000-4000-8000-000000000001",  # type: ignore[assignment]
            world_id="00000000-0000-4000-8000-000000000002",  # type: ignore[assignment]
            source_id="00000000-0000-4000-8000-000000000003",  # type: ignore[assignment]
            target_id="00000000-0000-4000-8000-000000000004",  # type: ignore[assignment]
            trust=12,
        ),
        "Ash",
    )


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


def test_relationship_endpoints_label_direction(client: ApiClient) -> None:
    headers = {"X-Worldsim-Role": "watcher"}
    ids = _run(_seed_pair())
    recorded = client.post(
        "/api/v1/stage2/relationships/evidence",
        json={
            "world_id": str(ids["world"]),
            "source_id": str(ids["wren"]),
            "target_id": str(ids["ash"]),
            "dimension": "affection",
            "delta": 4,
            "note": "shared rations",
        },
        headers=headers,
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["direction"] == "outgoing"
    listed = client.get(
        "/api/v1/stage2/relationships",
        params={"world_id": str(ids["world"]), "character_id": str(ids["ash"])},
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    members = listed.json()["members"]
    assert len(members) == 1
    assert members[0]["direction"] == "incoming"
    assert members[0]["affection"] == 4


def test_relationship_visibility_in_context() -> None:
    from worldsim.application.context.assembler import assemble
    from worldsim.domain.context import ContextRequest, SourceCandidate
    from worldsim.domain.enums import Visibility

    actor = new_character_id()
    other = new_character_id()
    request = ContextRequest(
        role="character_decision",
        actor_id=actor,
        world_id=new_world_id(),
        phase_run_id=new_world_id(),
        snapshot_id=new_world_id(),
        purpose="decide",
    )
    envelope, included, excluded = assemble(
        request,
        [
            SourceCandidate(
                source_id="rel:own",
                data_class="relationships",
                visibility=Visibility.PRIVATE,
                owner_id=actor,
                text="Ash: trust 5",
                score=1.5,
            ),
            SourceCandidate(
                source_id="rel:theirs",
                data_class="relationships",
                visibility=Visibility.PRIVATE,
                owner_id=other,
                text="Wren: trust -3",
                score=1.5,
            ),
        ],
    )
    assert [s.source_id for s in included] == ["rel:own"]
    assert [s.source_id for s in excluded] == ["rel:theirs"]
    assert "trust 5" in envelope.rendered
    assert "trust -3" not in envelope.rendered
