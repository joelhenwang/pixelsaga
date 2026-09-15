import asyncio
import json
import shutil
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from worldsim.application.commands.seed_world import ImportResult, SeedService
from worldsim.domain.characters import Character
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import (
    SqlAlchemyUnitOfWork,
    create_unit_of_work,
)
from worldsim.infrastructure.settings import Settings

SEED_DIR = Path(__file__).parent.parent.parent / "content" / "seeds" / "stage0"
WREN_ID = UUID("10000000-0000-4000-8000-000000000101")


def _factory_for(engine: AsyncEngine) -> Callable[[], SqlAlchemyUnitOfWork]:
    def _factory() -> SqlAlchemyUnitOfWork:
        return create_unit_of_work(engine)

    return _factory


@asynccontextmanager
async def _service(
    seed_dir: Path,
) -> AsyncGenerator[tuple[SeedService, AsyncEngine]]:
    engine = create_engine(Settings())
    try:
        yield SeedService(_factory_for(engine), seed_dir), engine
    finally:
        await engine.dispose()


async def _read_back(
    engine: AsyncEngine, world_id: UUID
) -> tuple[World, list[Location], list[Character], int]:
    async with create_unit_of_work(engine) as uow:
        world = await uow.worlds.get(world_id)
        places = await uow.locations.list_for_world(world_id)
        actors = await uow.characters.list_for_world(world_id)
        events = await uow.events.count_events(world_id)
        return world, places, actors, events


def test_import_creates_world_characters_and_secret(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _service(SEED_DIR) as (service, engine):
            result = await service.import_seed()
            assert result.seed_version == "stage0-v1"
            assert result.files == [
                "world.json",
                "locations.json",
                "characters.json",
                "lore.json",
            ]
            assert result.records == {
                "worlds": 1,
                "locations": 2,
                "characters": 2,
                "lore": 2,
                "secrets": 1,
            }
            assert not result.duplicate
            world, places, actors, events = await _read_back(engine, result.world_id)
            assert world.name == "Ember Vale"
            assert sorted(p.name for p in places) == ["Hearth", "Market"]
            assert sorted(c.name for c in actors) == ["Ash", "Wren"]
            assert events == 1

    asyncio.run(_inner())


def test_secret_ownership_and_lore_visibility(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _service(SEED_DIR) as (service, engine):
            result = await service.import_seed()
            async with create_unit_of_work(engine) as uow:
                memories = await uow.perception.memories_for_owner(WREN_ID)
                assert len(memories) == 1
                assert memories[0].owner_character_id == WREN_ID
                assert memories[0].visibility.value == "private"
                assert "rusted key" in memories[0].text
                config = await uow.worlds.get_config(result.world_id)
                assert "lore.well" in config
                command_id = await uow.commands.get_by_key(result.world_id, "seed:stage0-v1")
                assert command_id is not None
                event_id = await uow.commands.get_result(command_id)
                assert event_id is not None
                event = await uow.events.get_event(event_id)
                assert event.sequence == 1
                assert event.event_type.value == "world_seeded"

    asyncio.run(_inner())


def test_repeated_import_is_idempotent(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _service(SEED_DIR) as (service, engine):
            first = await service.import_seed()
            second = await service.import_seed()
            assert second.duplicate
            assert second.world_id == first.world_id
            assert second.content_hash == first.content_hash
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(first.world_id) == 1
                assert len(await uow.characters.list_for_world(first.world_id)) == 2

    asyncio.run(_inner())


def test_empty_import_fails_cleanly(migrated_db: None, tmp_path: Path) -> None:
    async def _inner() -> None:
        async with _service(tmp_path) as (service, _engine):
            with pytest.raises(DomainError) as excinfo:
                await service.import_seed()
            assert excinfo.value.code is ErrorCode.NOT_FOUND

    asyncio.run(_inner())


def _copied_seed(tmp_path: Path) -> Path:
    target = tmp_path / "stage0"
    shutil.copytree(SEED_DIR, target)
    return target


def _rewrite_json(path: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    mutate(doc)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def test_broken_reference_rolls_back(migrated_db: None, tmp_path: Path) -> None:
    async def _inner() -> None:
        broken = _copied_seed(tmp_path)
        _rewrite_json(
            broken / "characters.json",
            lambda doc: doc["characters"][0]["state"].update(
                {"location_id": "20000000-0000-4000-8000-000000000099"}
            ),
        )
        async with _service(broken) as (service, _engine):
            with pytest.raises(DomainError) as excinfo:
                await service.import_seed()
            assert excinfo.value.code is ErrorCode.VALIDATION_FAILED
            assert "unknown location" in str(excinfo.value)
        async with _service(SEED_DIR) as (valid, engine):
            result = await valid.import_seed()
            assert not result.duplicate
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(result.world_id) == 1

    asyncio.run(_inner())


def test_duplicate_id_rejected(migrated_db: None, tmp_path: Path) -> None:
    async def _inner() -> None:
        broken = _copied_seed(tmp_path)
        _rewrite_json(
            broken / "characters.json",
            lambda doc: doc["characters"][1].update({"id": doc["characters"][0]["id"]}),
        )
        async with _service(broken) as (service, _engine):
            with pytest.raises(DomainError) as excinfo:
                await service.import_seed()
            assert excinfo.value.code is ErrorCode.VALIDATION_FAILED
            assert "duplicate" in str(excinfo.value)

    asyncio.run(_inner())


def test_result_carries_report_fields(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _service(SEED_DIR) as (service, _engine):
            result: ImportResult = await service.import_seed()
            assert result.content_hash and len(result.content_hash) == 64
            assert result.world_id is not None

    asyncio.run(_inner())
