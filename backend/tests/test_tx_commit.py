import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from uuid import UUID

import pytest

from worldsim.application.transactions.canonical import (
    CanonicalTransaction,
    CommitRequest,
    MemorySpec,
    ObservationSpec,
    OutboxSpec,
    canonical_input_hash,
)
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.effects import AdvanceClockEffect, DomainEffect, ResourceAdjustedEffect
from worldsim.domain.enums import EventType, ResourceKind
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    new_card_id,
    new_character_id,
    new_command_id,
    new_location_id,
    new_phase_run_id,
    new_world_id,
)
from worldsim.domain.perception import ObservationFact
from worldsim.domain.phases import PhaseRun
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


@asynccontextmanager
async def _service(
    hook: Callable[[str], None] | None = None,
) -> AsyncGenerator[CanonicalTransaction]:
    engine = create_engine(Settings())
    try:
        yield CanonicalTransaction(lambda: create_unit_of_work(engine), pre_commit_hook=hook)
    finally:
        await engine.dispose()


async def _seed_tx() -> tuple[UUID, UUID, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            await uow.worlds.add(World(id=wid, name="Tx", seed_version="s0-test"))
            home = new_location_id()
            await uow.locations.add(Location(id=home, world_id=wid, name="Hearth"))
            cid = new_character_id()
            await uow.characters.add_identity(cid, wid, "Wren")
            await uow.characters.add_card(
                CharacterCard(id=new_card_id(), character_id=cid, name="W", version=1)
            )
            await uow.characters.add_state(
                Character(
                    id=cid,
                    world_id=wid,
                    name="Wren",
                    card_version=1,
                    location_id=home,
                    stamina=80,
                    mana=40,
                )
            )
            await uow.versions.ensure(wid, wid, "world")
            await uow.versions.ensure(cid, wid, "character")
            run_id = new_phase_run_id()
            await uow.phases.create_run(PhaseRun(id=run_id, world_id=wid, absolute_index=1))
            await uow.commit()
            return wid, cid, run_id
    finally:
        await engine.dispose()


def _tick_request(
    wid: UUID,
    cid: UUID,
    run_id: UUID,
    key: str,
    versions: dict[str, int] | None = None,
) -> CommitRequest:
    payload: dict[str, object] = {"absolute_index": 1, "note": "first tick"}
    base = versions if versions is not None else {str(wid): 0, str(cid): 0}
    effects: list[DomainEffect] = [
        AdvanceClockEffect(
            affected_ids=[wid],
            expected_versions={str(wid): base[str(wid)]},
            from_index=0,
            to_index=1,
        ),
        ResourceAdjustedEffect(
            affected_ids=[cid],
            expected_versions={str(cid): base[str(cid)]},
            resource=ResourceKind.STAMINA,
            delta=-5,
        ),
    ]
    return CommitRequest(
        command_id=new_command_id(),
        world_id=wid,
        idempotency_key=key,
        actor_role="system",
        command_type="advance_phase",
        expected_versions=base,
        payload=payload,
        input_hash=canonical_input_hash(
            {
                "key": key,
                "payload": payload,
                "effects": [e.model_dump(mode="json") for e in effects],
            }
        ),
        absolute_index=1,
        phase_run_id=run_id,
        event_type=EventType.WORLD_TICKED,
        effects=effects,
        observations=[
            ObservationSpec(observer_id=cid, facts=[ObservationFact(key="light", value="dawn")])
        ],
        memories=[MemorySpec(owner_id=cid, text="Dawn came.", observation_index=0)],
        outbox=[OutboxSpec(kind="phase_followup", payload={"phase": 1}, key=f"{key}:out")],
    )


def test_commit_success_creates_coherent_result(migrated_db: None) -> None:
    async def _inner() -> None:
        wid, cid, run_id = await _seed_tx()
        async with _service() as tx:
            result = await tx.commit(_tick_request(wid, cid, run_id, "tick-1"))
        assert result.sequence == 1
        assert result.effect_count == 2
        assert result.versions == {str(wid): 1, str(cid): 1}
        assert len(result.observation_ids) == 1
        assert len(result.memory_ids) == 1
        assert len(result.outbox_ids) == 1
        assert not result.duplicate
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(wid) == 1
                assert len(await uow.events.list_effects(result.event_id)) == 2
                world = await uow.worlds.get(wid)
                assert (world.day, world.phase.value) == (1, "sunrise")
                assert await uow.worlds.get_clock(wid) == (1, "sunrise", 1)
                assert (await uow.characters.get(cid)).stamina == 75
                assert await uow.outbox.count_pending(wid) == 1
                assert len(await uow.perception.memories_for_owner(cid)) == 1
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_version_mismatch_creates_no_event(migrated_db: None) -> None:
    async def _inner() -> None:
        wid, cid, run_id = await _seed_tx()
        async with _service() as tx:
            request = _tick_request(
                wid, cid, run_id, "tick-bad", versions={str(wid): 9, str(cid): 0}
            )
            with pytest.raises(DomainError) as excinfo:
                await tx.commit(request)
            assert excinfo.value.code is ErrorCode.VERSION_CONFLICT
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(wid) == 0
                assert await uow.commands.get_by_key(wid, "tick-bad") is None
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_fault_at_each_step_rolls_back(migrated_db: None) -> None:
    async def _inner() -> None:
        wid, cid, run_id = await _seed_tx()
        for point in (
            "after_command",
            "after_effects",
            "after_projections",
            "after_perception",
            "after_outbox",
        ):

            def _hook(_point: str, _wanted: str = point) -> None:
                if _point == _wanted:
                    raise RuntimeError(f"injected at {_point}")

            async with _service(hook=_hook) as tx:
                with pytest.raises(RuntimeError, match="injected"):
                    await tx.commit(_tick_request(wid, cid, run_id, f"tick-{point}"))
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(wid) == 0
                assert await uow.versions.get(wid) == 0
                assert await uow.commands.get_by_key(wid, "tick-after_command") is None
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_duplicate_returns_original_result(migrated_db: None) -> None:
    async def _inner() -> None:
        wid, cid, run_id = await _seed_tx()
        async with _service() as tx:
            first = await tx.commit(_tick_request(wid, cid, run_id, "tick-dup"))
            second = await tx.commit(_tick_request(wid, cid, run_id, "tick-dup"))
        assert second.duplicate
        assert second.event_id == first.event_id
        assert second.sequence == first.sequence
        assert second.versions == first.versions
        assert second.observation_ids == first.observation_ids
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(wid) == 1
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_same_key_different_input_conflicts(migrated_db: None) -> None:
    async def _inner() -> None:
        wid, cid, run_id = await _seed_tx()
        async with _service() as tx:
            await tx.commit(_tick_request(wid, cid, run_id, "tick-key"))
            other = _tick_request(wid, cid, run_id, "tick-key")
            tampered = CommitRequest(
                command_id=other.command_id,
                world_id=other.world_id,
                idempotency_key=other.idempotency_key,
                actor_role=other.actor_role,
                command_type=other.command_type,
                expected_versions=other.expected_versions,
                payload={"absolute_index": 2, "note": "tampered"},
                input_hash=canonical_input_hash({"tampered": True}),
                absolute_index=other.absolute_index,
                phase_run_id=other.phase_run_id,
                event_type=other.event_type,
                effects=other.effects,
                observations=list(other.observations),
                memories=list(other.memories),
                outbox=list(other.outbox),
            )
            with pytest.raises(DomainError) as excinfo:
                await tx.commit(tampered)
            assert excinfo.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(wid) == 1
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_two_stale_writers_only_one_commits(migrated_db: None) -> None:
    async def _inner() -> None:
        wid, cid, run_id = await _seed_tx()
        async with _service() as first:
            await first.commit(_tick_request(wid, cid, run_id, "tick-a"))
        async with _service() as second:
            with pytest.raises(DomainError) as excinfo:
                await second.commit(_tick_request(wid, cid, run_id, "tick-b"))
            assert excinfo.value.code is ErrorCode.VERSION_CONFLICT
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(wid) == 1
        finally:
            await engine.dispose()

    asyncio.run(_inner())
