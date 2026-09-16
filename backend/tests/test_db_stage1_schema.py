"""Stage 1 tables accept valid scene rows and enforce key invariants (owned by S1-CONTRACT-001)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.models.characters import CharacterRow
from worldsim.infrastructure.models.events import WorldEventRow
from worldsim.infrastructure.models.phases import PhaseRunRow, PhaseSnapshotRow
from worldsim.infrastructure.models.scenes import (
    AttemptRow,
    CharacterIntentRow,
    NarrationRow,
    ReactionRow,
    ResolutionRow,
    SceneParticipantRow,
    SceneRow,
)
from worldsim.infrastructure.models.world import EntityRow, WorldClockRow, WorldRow
from worldsim.infrastructure.settings import Settings


async def _add(session: AsyncSession, row: object) -> None:
    session.add(row)
    await session.flush()


async def _parents(session: AsyncSession) -> dict[str, uuid.UUID]:
    wid = uuid.uuid4()
    await _add(session, WorldRow(id=wid, name="Vale", seed_version="s1-test"))
    await _add(session, WorldClockRow(world_id=wid, day=1, phase="dawn", absolute_index=0))
    run_id = uuid.uuid4()
    await _add(session, PhaseRunRow(id=run_id, world_id=wid, absolute_index=1))
    snap_id = uuid.uuid4()
    await _add(
        session,
        PhaseSnapshotRow(
            id=snap_id,
            world_id=wid,
            phase_run_id=run_id,
            absolute_index=1,
            world_version=1,
            content_hash="b" * 64,
        ),
    )
    characters = {}
    for name in ("Wren", "Ash"):
        cid = uuid.uuid4()
        await _add(
            session, EntityRow(id=cid, world_id=wid, kind="character", created_phase_index=0)
        )
        await _add(session, CharacterRow(id=cid, world_id=wid, name=name))
        characters[name] = cid
    event_id = uuid.uuid4()
    await _add(
        session,
        WorldEventRow(
            id=event_id,
            world_id=wid,
            sequence=1,
            event_type="action_resolved",
            absolute_index=1,
            phase_run_id=run_id,
            participant_ids=[],
            summary={},
        ),
    )
    await session.commit()
    return {"world": wid, "run": run_id, "snapshot": snap_id, "event": event_id, **characters}


def test_scene_tables_accept_valid_rows(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            async with AsyncSession(engine) as session:
                ids = await _parents(session)
                intent_id = uuid.uuid4()
                await _add(
                    session,
                    CharacterIntentRow(
                        id=intent_id,
                        world_id=ids["world"],
                        snapshot_id=ids["snapshot"],
                        phase_run_id=ids["run"],
                        author_character_id=ids["Wren"],
                        family="communicate",
                        intent={"family": "communicate", "topic": "the market road"},
                        idempotency_key="intent-wren-1",
                    ),
                )
                scene_id = uuid.uuid4()
                await _add(
                    session,
                    SceneRow(
                        id=scene_id,
                        world_id=ids["world"],
                        phase_run_id=ids["run"],
                        snapshot_id=ids["snapshot"],
                    ),
                )
                await _add(
                    session,
                    SceneParticipantRow(
                        scene_id=scene_id, character_id=ids["Wren"], role="initiator"
                    ),
                )
                await _add(
                    session,
                    SceneParticipantRow(scene_id=scene_id, character_id=ids["Ash"], role="reactor"),
                )
                attempt_id = uuid.uuid4()
                await _add(
                    session,
                    AttemptRow(
                        id=attempt_id,
                        world_id=ids["world"],
                        scene_id=scene_id,
                        intent_id=intent_id,
                        actor_character_id=ids["Wren"],
                        observable_summary="Wren hails Ash.",
                    ),
                )
                await _add(
                    session,
                    ReactionRow(
                        id=uuid.uuid4(),
                        world_id=ids["world"],
                        attempt_id=attempt_id,
                        scene_id=scene_id,
                        reactor_character_id=ids["Ash"],
                        reaction={"family": "wait"},
                    ),
                )
                await _add(
                    session,
                    ResolutionRow(
                        id=uuid.uuid4(),
                        world_id=ids["world"],
                        scene_id=scene_id,
                        resolver="deterministic",
                        outcome="success",
                        effects=[],
                        rationale="they talked",
                    ),
                )
                await _add(
                    session,
                    NarrationRow(
                        id=uuid.uuid4(),
                        world_id=ids["world"],
                        scene_id=scene_id,
                        event_id=ids["event"],
                        speaker_character_id=ids["Wren"],
                        kind="dialogue",
                        text="Take the market road.",
                    ),
                )
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_one_intent_per_character_per_snapshot(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            async with AsyncSession(engine) as session:
                ids = await _parents(session)
                await _add(
                    session,
                    CharacterIntentRow(
                        id=uuid.uuid4(),
                        world_id=ids["world"],
                        snapshot_id=ids["snapshot"],
                        author_character_id=ids["Wren"],
                        family="wait",
                        intent={"family": "wait"},
                        idempotency_key="intent-wren-1",
                    ),
                )
                await session.commit()
                session.add(
                    CharacterIntentRow(
                        id=uuid.uuid4(),
                        world_id=ids["world"],
                        snapshot_id=ids["snapshot"],
                        author_character_id=ids["Wren"],
                        family="observe",
                        intent={"family": "observe"},
                        idempotency_key="intent-wren-2",
                    ),
                )
                with pytest.raises(IntegrityError):
                    await session.flush()
                await session.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_attempt_reaction_resolution_uniqueness(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            async with AsyncSession(engine) as session:
                ids = await _parents(session)
                intent_id = uuid.uuid4()
                await _add(
                    session,
                    CharacterIntentRow(
                        id=intent_id,
                        world_id=ids["world"],
                        snapshot_id=ids["snapshot"],
                        author_character_id=ids["Wren"],
                        family="wait",
                        intent={"family": "wait"},
                        idempotency_key="intent-wren-1",
                    ),
                )
                await _add(
                    session,
                    AttemptRow(
                        id=uuid.uuid4(),
                        world_id=ids["world"],
                        intent_id=intent_id,
                        actor_character_id=ids["Wren"],
                        observable_summary="Wren waits.",
                    ),
                )
                await session.commit()
                session.add(
                    AttemptRow(
                        id=uuid.uuid4(),
                        world_id=ids["world"],
                        intent_id=intent_id,
                        actor_character_id=ids["Wren"],
                        observable_summary="Wren waits again.",
                    ),
                )
                with pytest.raises(IntegrityError):
                    await session.flush()
                await session.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_inner())
