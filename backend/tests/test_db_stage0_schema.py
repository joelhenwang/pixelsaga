import asyncio
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from psycopg import connect
from psycopg.errors import DuplicateDatabase
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.infrastructure.db.engine import create_engine, session_factory
from worldsim.infrastructure.db.urls import to_sync_url
from worldsim.infrastructure.models.calls import (
    ContextManifestRow,
    ModelCallRow,
    ModelProfileRow,
)
from worldsim.infrastructure.models.characters import (
    CharacterCardVersionRow,
    CharacterRow,
    CharacterStateRow,
)
from worldsim.infrastructure.models.commands import UserCommandRow
from worldsim.infrastructure.models.events import EventEffectRow, WorldEventRow
from worldsim.infrastructure.models.perception import ObservationRow, RecentMemoryRow
from worldsim.infrastructure.models.phases import (
    PhaseRunRow,
    PhaseSnapshotCharacterRow,
    PhaseSnapshotRow,
)
from worldsim.infrastructure.models.tasks import OutboxMessageRow, TaskRunRow
from worldsim.infrastructure.models.versions import AggregateVersionRow
from worldsim.infrastructure.models.world import (
    EntityRow,
    LocationRow,
    WorldClockRow,
    WorldConfigRow,
    WorldRow,
)
from worldsim.infrastructure.settings import Settings

SCRATCH_DB = "worldsim_schema_test"


async def _add(session: AsyncSession, row: object) -> None:
    """Add one row and flush immediately: without ORM relationships the
    unit of work emits unordered inserts, so seeds (like the future
    canonical transaction) order parents before children explicitly."""
    session.add(row)
    await session.flush()


def _replace_database(url: str, database: str) -> str:
    parts = urlparse(url)
    return urlunparse(parts._replace(path=f"/{database}"))


@pytest.fixture
def migrated_scratch(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    base = to_sync_url(Settings().database.url)
    admin = connect(_replace_database(base, "postgres"), autocommit=True)
    try:
        try:
            admin.execute(f"CREATE DATABASE {SCRATCH_DB}")
        except DuplicateDatabase:
            pass
    finally:
        admin.close()
    monkeypatch.setenv(
        "WORLDSIM_DATABASE__URL", _replace_database(Settings().database.url, SCRATCH_DB)
    )
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent.parent / "migrations"))
    alembic_command.upgrade(config, "head")
    yield
    admin = connect(_replace_database(base, "postgres"), autocommit=True)
    try:
        admin.execute(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)")
    finally:
        admin.close()


async def _seed_world() -> uuid.UUID:
    engine = create_engine(Settings())
    try:
        sessions = session_factory(engine)
        async with sessions() as session:
            wid = uuid.uuid4()
            await _add(session, WorldRow(id=wid, name="Probe", seed_version="s0-test"))
            await _add(session, WorldClockRow(world_id=wid, day=1, phase="dawn", absolute_index=0))
            await session.commit()
            return wid
    finally:
        await engine.dispose()


async def _seed_character(
    world_id: uuid.UUID, location_id: uuid.UUID | None = None
) -> tuple[uuid.UUID, uuid.UUID]:
    engine = create_engine(Settings())
    try:
        sessions = session_factory(engine)
        async with sessions() as session:
            home = location_id or uuid.uuid4()
            if location_id is None:
                await _add(
                    session,
                    EntityRow(id=home, world_id=world_id, kind="location", created_phase_index=0),
                )
                await _add(session, LocationRow(id=home, world_id=world_id, name="Hearth"))
            cid = uuid.uuid4()
            await _add(
                session,
                EntityRow(id=cid, world_id=world_id, kind="character", created_phase_index=0),
            )
            await _add(session, CharacterRow(id=cid, world_id=world_id, name="Wren"))
            await _add(session, CharacterCardVersionRow(character_id=cid, version=1, name="Wren"))
            await _add(
                session,
                CharacterStateRow(
                    character_id=cid,
                    world_id=world_id,
                    card_version=1,
                    location_id=home,
                    stamina=80,
                    mana=40,
                    conditions=[],
                ),
            )
            await session.commit()
            return cid, home
    finally:
        await engine.dispose()


def test_full_stage0_row_graph_persists(migrated_scratch: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            sessions = session_factory(engine)
            async with sessions() as session:
                wid = uuid.uuid4()
                await _add(session, WorldRow(id=wid, name="Full", seed_version="s0-full"))
                await _add(
                    session, WorldConfigRow(world_id=wid, key="theme", value={"tone": "soft-dark"})
                )
                await _add(
                    session, WorldClockRow(world_id=wid, day=2, phase="noon", absolute_index=13)
                )
                home = uuid.uuid4()
                await _add(
                    session,
                    EntityRow(id=home, world_id=wid, kind="location", created_phase_index=0),
                )
                await _add(session, LocationRow(id=home, world_id=wid, name="Hearth", routes=[]))
                cid = uuid.uuid4()
                await _add(
                    session,
                    EntityRow(id=cid, world_id=wid, kind="character", created_phase_index=0),
                )
                await _add(session, CharacterRow(id=cid, world_id=wid, name="Wren"))
                await _add(
                    session, CharacterCardVersionRow(character_id=cid, version=1, name="Wren")
                )
                await _add(
                    session,
                    CharacterStateRow(
                        character_id=cid,
                        world_id=wid,
                        card_version=1,
                        location_id=home,
                        stamina=80,
                        mana=40,
                        conditions=[],
                    ),
                )
                run_id = uuid.uuid4()
                await _add(
                    session,
                    PhaseRunRow(id=run_id, world_id=wid, absolute_index=13, state="completed"),
                )
                snap_id = uuid.uuid4()
                await _add(
                    session,
                    PhaseSnapshotRow(
                        id=snap_id,
                        world_id=wid,
                        phase_run_id=run_id,
                        absolute_index=13,
                        world_version=2,
                        content_hash="a" * 64,
                    ),
                )
                await _add(
                    session,
                    PhaseSnapshotCharacterRow(snapshot_id=snap_id, character_id=cid, version=0),
                )
                cmd_id = uuid.uuid4()
                await _add(
                    session,
                    UserCommandRow(
                        id=cmd_id,
                        world_id=wid,
                        idempotency_key="cmd-1",
                        actor_role="system",
                        command_type="advance_phase",
                        expected_versions={},
                        payload={},
                        input_hash="b" * 64,
                    ),
                )
                event_id = uuid.uuid4()
                await _add(
                    session,
                    WorldEventRow(
                        id=event_id,
                        world_id=wid,
                        sequence=1,
                        event_type="action_resolved",
                        absolute_index=13,
                        phase_run_id=run_id,
                        source_command_id=cmd_id,
                        participant_ids=[str(cid)],
                        summary={"k": "v"},
                    ),
                )
                await _add(
                    session,
                    EventEffectRow(
                        event_id=event_id,
                        ordinal=0,
                        effect_type="resource_adjusted",
                        payload={"resource": "stamina", "delta": -5},
                    ),
                )
                obs_id = uuid.uuid4()
                await _add(
                    session,
                    ObservationRow(
                        id=obs_id,
                        world_id=wid,
                        event_id=event_id,
                        observer_character_id=cid,
                        facts=[{"key": "weather", "value": "cold"}],
                        created_phase_index=13,
                    ),
                )
                await _add(
                    session,
                    RecentMemoryRow(
                        id=uuid.uuid4(),
                        world_id=wid,
                        owner_character_id=cid,
                        event_id=event_id,
                        observation_id=obs_id,
                        text="Cold dawn.",
                        created_phase_index=13,
                    ),
                )
                await _add(
                    session,
                    AggregateVersionRow(
                        aggregate_id=cid, world_id=wid, kind="character", version=1
                    ),
                )
                task_id = uuid.uuid4()
                await _add(
                    session,
                    TaskRunRow(
                        id=task_id, world_id=wid, kind="phase_advance", idempotency_key="task-1"
                    ),
                )
                await _add(
                    session,
                    OutboxMessageRow(
                        id=uuid.uuid4(),
                        world_id=wid,
                        event_id=event_id,
                        kind="phase_followup",
                        payload={},
                        idempotency_key="out-1",
                    ),
                )
                await _add(
                    session,
                    ModelProfileRow(
                        name="fake",
                        version="test-v1",
                        adapter="fake",
                        model_id="fake-echo",
                        max_context_tokens=4096,
                        capabilities=["chat"],
                    ),
                )
                call_id = uuid.uuid4()
                await _add(
                    session,
                    ModelCallRow(
                        id=call_id,
                        world_id=wid,
                        profile_name="fake",
                        profile_version="test-v1",
                        status="succeeded",
                        request={"prompt": "hi"},
                        result={"text": "yo"},
                        prompt_tokens=1,
                        completion_tokens=1,
                        latency_ms=2,
                    ),
                )
                await _add(
                    session,
                    ContextManifestRow(
                        call_id=call_id,
                        world_id=wid,
                        sources=[{"kind": "memory"}],
                        budgets={"tokens": 100},
                    ),
                )
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_duplicate_event_sequence_rejected(migrated_scratch: None) -> None:
    async def _inner() -> None:
        wid = await _seed_world()
        engine = create_engine(Settings())
        try:
            sessions = session_factory(engine)
            async with sessions() as session:
                await _add(
                    session,
                    WorldEventRow(
                        id=uuid.uuid4(),
                        world_id=wid,
                        sequence=1,
                        event_type="world_ticked",
                        absolute_index=0,
                    ),
                )
                await session.commit()
                session.add(
                    WorldEventRow(
                        id=uuid.uuid4(),
                        world_id=wid,
                        sequence=1,
                        event_type="world_ticked",
                        absolute_index=0,
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_duplicate_effect_ordinal_rejected(migrated_scratch: None) -> None:
    async def _inner() -> None:
        wid = await _seed_world()
        engine = create_engine(Settings())
        try:
            sessions = session_factory(engine)
            async with sessions() as session:
                event_id = uuid.uuid4()
                await _add(
                    session,
                    WorldEventRow(
                        id=event_id,
                        world_id=wid,
                        sequence=1,
                        event_type="world_ticked",
                        absolute_index=0,
                    ),
                )
                await _add(
                    session,
                    EventEffectRow(
                        event_id=event_id,
                        ordinal=0,
                        effect_type="advance_clock",
                        payload={},
                    ),
                )
                await session.commit()
                session.add(
                    EventEffectRow(
                        event_id=event_id,
                        ordinal=0,
                        effect_type="advance_clock",
                        payload={},
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_duplicate_command_key_rejected(migrated_scratch: None) -> None:
    async def _inner() -> None:
        wid = await _seed_world()
        engine = create_engine(Settings())
        try:
            sessions = session_factory(engine)
            async with sessions() as session:
                await _add(
                    session,
                    UserCommandRow(
                        id=uuid.uuid4(),
                        world_id=wid,
                        idempotency_key="cmd-dup",
                        actor_role="system",
                        command_type="advance_phase",
                        expected_versions={},
                        payload={},
                        input_hash="c" * 64,
                    ),
                )
                await session.commit()
                session.add(
                    UserCommandRow(
                        id=uuid.uuid4(),
                        world_id=wid,
                        idempotency_key="cmd-dup",
                        actor_role="system",
                        command_type="advance_phase",
                        expected_versions={},
                        payload={},
                        input_hash="d" * 64,
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_snapshot_mutation_rejected(migrated_scratch: None) -> None:
    async def _inner() -> None:
        wid = await _seed_world()
        engine = create_engine(Settings())
        try:
            sessions = session_factory(engine)
            async with sessions() as session:
                run_id = uuid.uuid4()
                await _add(session, PhaseRunRow(id=run_id, world_id=wid, absolute_index=0))
                snap_id = uuid.uuid4()
                await _add(
                    session,
                    PhaseSnapshotRow(
                        id=snap_id,
                        world_id=wid,
                        phase_run_id=run_id,
                        absolute_index=0,
                        world_version=0,
                        content_hash="e" * 64,
                    ),
                )
                await session.commit()
                snapshot = await session.get(PhaseSnapshotRow, snap_id)
                assert snapshot is not None
                snapshot.world_version = 99
                with pytest.raises(DBAPIError, match="immutable"):
                    await session.commit()
                await session.rollback()
                snapshot = await session.get(PhaseSnapshotRow, snap_id)
                assert snapshot is not None
                await session.delete(snapshot)
                with pytest.raises(DBAPIError, match="immutable"):
                    await session.commit()
                await session.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_invalid_ranges_rejected(migrated_scratch: None) -> None:
    async def _inner() -> None:
        wid = await _seed_world()
        cid, _ = await _seed_character(wid)
        engine = create_engine(Settings())
        try:
            sessions = session_factory(engine)
            async with sessions() as session:
                state = await session.get(CharacterStateRow, cid)
                assert state is not None
                state.stamina = 101
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()
                session.add(
                    WorldEventRow(
                        id=uuid.uuid4(),
                        world_id=wid,
                        sequence=0,
                        event_type="world_ticked",
                        absolute_index=0,
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()
                clock = await session.get(WorldClockRow, wid)
                assert clock is not None
                clock.day = 0
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_missing_source_links_rejected(migrated_scratch: None) -> None:
    async def _inner() -> None:
        wid = await _seed_world()
        engine = create_engine(Settings())
        try:
            sessions = session_factory(engine)
            async with sessions() as session:
                session.add(
                    EventEffectRow(
                        event_id=uuid.uuid4(),
                        ordinal=0,
                        effect_type="advance_clock",
                        payload={},
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()
                session.add(
                    ObservationRow(
                        id=uuid.uuid4(),
                        world_id=wid,
                        event_id=uuid.uuid4(),
                        observer_character_id=uuid.uuid4(),
                        facts=[],
                        created_phase_index=0,
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()
                session.add(
                    RecentMemoryRow(
                        id=uuid.uuid4(),
                        world_id=wid,
                        owner_character_id=uuid.uuid4(),
                        observation_id=uuid.uuid4(),
                        text="x",
                        created_phase_index=0,
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_inner())
