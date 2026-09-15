import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest

from worldsim.application.ports.repositories import canonical_order
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.effects import ResourceAdjustedEffect
from worldsim.domain.enums import EventType, ResourceKind
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.events import CommittedEffect, WorldEvent
from worldsim.domain.ids import (
    new_character_id,
    new_command_id,
    new_event_id,
    new_location_id,
    new_memory_id,
    new_observation_id,
    new_outbox_id,
    new_phase_run_id,
    new_snapshot_id,
    new_task_id,
    new_world_id,
)
from worldsim.domain.perception import Observation, ObservationFact, RecentMemory
from worldsim.domain.phases import PhaseRun, PhaseSnapshot, SnapshotCharacter
from worldsim.domain.tasks import Lease, OutboxMessage
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import (
    SqlAlchemyUnitOfWork,
    create_unit_of_work,
)
from worldsim.infrastructure.settings import Settings


@asynccontextmanager
async def _open() -> AsyncGenerator[SqlAlchemyUnitOfWork]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            yield uow
    finally:
        await engine.dispose()


def _world() -> World:
    return World(id=new_world_id(), name="Probe", seed_version="s0-test")


def _character(world_id: uuid.UUID, location_id: uuid.UUID) -> Character:
    return Character(
        id=new_character_id(),
        world_id=world_id,
        name="Wren",
        card_version=1,
        location_id=location_id,
        stamina=80,
        mana=40,
    )


async def _seed_place(uow: SqlAlchemyUnitOfWork) -> tuple[World, Location]:
    world = _world()
    await uow.worlds.add(world)
    place = Location(id=new_location_id(), world_id=world.id, name="Hearth")
    await uow.locations.add(place)
    return world, place


def test_world_crud_config_clock_and_versions(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _open() as uow:
            world = _world()
            await uow.worlds.add(world)
            assert await uow.worlds.get(world.id) == world
            await uow.worlds.put_config(world.id, "theme", {"tone": "soft-dark"})
            assert await uow.worlds.get_config(world.id) == {"theme": {"tone": "soft-dark"}}
            assert await uow.worlds.get_clock(world.id) == (1, "dawn", 0)
            await uow.worlds.set_clock(world.id, 1, "noon", 3)
            assert await uow.worlds.get_clock(world.id) == (1, "noon", 3)
            saved = await uow.worlds.save(
                world.model_copy(update={"name": "Ember"}), expected_version=0
            )
            assert saved.version == 1
            with pytest.raises(DomainError) as excinfo:
                await uow.worlds.save(world, expected_version=0)
            assert excinfo.value.code is ErrorCode.VERSION_CONFLICT
            await uow.commit()
        async with _open() as uow:
            assert (await uow.worlds.get(world.id)).name == "Ember"
            with pytest.raises(DomainError) as excinfo:
                await uow.worlds.get(new_world_id())
            assert excinfo.value.code is ErrorCode.NOT_FOUND

    asyncio.run(_inner())


def test_character_bundle_round_trip(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _open() as uow:
            world, place = await _seed_place(uow)
            first = _character(world.id, place.id)
            second = _character(world.id, place.id)
            for character in (first, second):
                await uow.characters.add_identity(character.id, world.id, character.name)
                await uow.characters.add_card(
                    CharacterCard(
                        id=uuid.uuid4(),
                        character_id=character.id,
                        name=character.name,
                        version=1,
                    )
                )
                await uow.characters.add_state(character)
            assert await uow.characters.get(first.id) == first
            assert len(await uow.characters.list_for_world(world.id)) == 2
            card = await uow.characters.get_card(first.id, 1)
            assert card.name == first.name
            moved = first.model_copy(update={"stamina": 70})
            saved = await uow.characters.save_state(moved, expected_version=0)
            assert saved.version == 1
            await uow.commit()
            assert (await uow.characters.get(first.id)).stamina == 70

    asyncio.run(_inner())


def test_location_routes_round_trip(migrated_db: None) -> None:
    async def _inner() -> None:
        from worldsim.domain.world import Route

        async with _open() as uow:
            world = _world()
            await uow.worlds.add(world)
            market = Location(
                id=new_location_id(), world_id=world.id, name="Market", discovered=True
            )
            await uow.locations.add(market)
            home = Location(
                id=new_location_id(),
                world_id=world.id,
                name="Hearth",
                routes=[
                    Route(
                        id=uuid.uuid4(),
                        destination_location_id=market.id,
                        duration_phases=2,
                        stamina_cost=15,
                    )
                ],
            )
            await uow.locations.add(home)
            assert await uow.locations.get(home.id) == home
            assert [place.name for place in await uow.locations.list_for_world(world.id)] == [
                "Hearth",
                "Market",
            ]
            await uow.commit()

    asyncio.run(_inner())


def test_phase_run_and_snapshot(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _open() as uow:
            world, place = await _seed_place(uow)
            character = _character(world.id, place.id)
            await uow.characters.add_identity(character.id, world.id, character.name)
            await uow.characters.add_card(
                CharacterCard(id=uuid.uuid4(), character_id=character.id, name="x", version=1)
            )
            await uow.characters.add_state(character)
            run = PhaseRun(id=new_phase_run_id(), world_id=world.id, absolute_index=0)
            await uow.phases.create_run(run)
            await uow.phases.set_run_state(run.id, "snapshot_sealed")
            assert (await uow.phases.get_run(run.id)).state.value == "snapshot_sealed"
            snapshot = PhaseSnapshot(
                id=new_snapshot_id(),
                world_id=world.id,
                phase_run_id=run.id,
                absolute_index=0,
                world_version=0,
                characters=[SnapshotCharacter(character_id=character.id, version=0)],
                content_hash="f" * 64,
            )
            await uow.phases.add_snapshot(snapshot)
            assert await uow.phases.get_snapshot(snapshot.id) == snapshot
            await uow.commit()

    asyncio.run(_inner())


def test_event_command_and_version_records(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _open() as uow:
            world, place = await _seed_place(uow)
            character = _character(world.id, place.id)
            await uow.characters.add_identity(character.id, world.id, character.name)
            await uow.characters.add_card(
                CharacterCard(id=uuid.uuid4(), character_id=character.id, name="x", version=1)
            )
            await uow.characters.add_state(character)
            command_id = new_command_id()
            await uow.commands.add(
                command_id=command_id,
                world_id=world.id,
                key="cmd-1",
                actor_role="system",
                command_type="advance_phase",
                expected_versions={str(character.id): 0},
                payload={},
                input_hash="ab" * 32,
            )
            assert await uow.commands.get_by_key(world.id, "cmd-1") == command_id
            assert await uow.commands.get_input_hash(command_id) == "ab" * 32
            assert await uow.commands.get_result(command_id) is None
            run_id = new_phase_run_id()
            await uow.phases.create_run(PhaseRun(id=run_id, world_id=world.id, absolute_index=0))
            event = WorldEvent(
                id=new_event_id(),
                world_id=world.id,
                sequence=1,
                event_type=EventType.ACTION_RESOLVED,
                absolute_index=0,
                phase_run_id=run_id,
                source_command_id=command_id,
                participant_ids=[character.id],
            )
            await uow.events.append_event(event)
            assert await uow.events.max_sequence(world.id) == 1
            effect = CommittedEffect(
                event_id=event.id,
                ordinal=0,
                effect=ResourceAdjustedEffect(
                    affected_ids=[character.id],
                    expected_versions={str(character.id): 0},
                    resource=ResourceKind.STAMINA,
                    delta=-5,
                ),
            )
            await uow.events.append_effect(effect)
            assert await uow.events.get_event(event.id) == event
            assert await uow.events.list_effects(event.id) == [effect]
            assert await uow.events.count_events(world.id) == 1
            await uow.commands.set_result(command_id, event.id)
            assert await uow.commands.get_result(command_id) == event.id
            await uow.versions.ensure(character.id, world.id, "character")
            assert await uow.versions.get(character.id) == 0
            bumped = await uow.versions.compare_and_bump({character.id: 0})
            assert bumped == {character.id: 1}
            await uow.commit()

    asyncio.run(_inner())


def test_task_outbox_perception_round_trips(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _open() as uow:
            world, place = await _seed_place(uow)
            character = _character(world.id, place.id)
            await uow.characters.add_identity(character.id, world.id, character.name)
            await uow.characters.add_card(
                CharacterCard(id=uuid.uuid4(), character_id=character.id, name="x", version=1)
            )
            await uow.characters.add_state(character)
            task = await uow.tasks.create(new_task_id(), world.id, "phase_advance", "task-1")
            assert (await uow.tasks.get(task.id)).state.value == "pending"
            now = datetime.now(UTC)
            lease = Lease(
                owner="worker-a",
                claimed_at=now,
                expires_at=now + timedelta(seconds=60),
                attempt=1,
                max_attempts=3,
                input_version=1,
                idempotency_key="task-1",
            )
            claimed = await uow.tasks.claim(task.id, "worker-a", lease)
            assert claimed is not None and claimed.lease is not None
            assert await uow.tasks.heartbeat(task.id, "worker-a", now + timedelta(seconds=120))
            message = OutboxMessage(
                id=new_outbox_id(),
                world_id=world.id,
                event_id=None,
                kind="phase_followup",
                payload={},
                idempotency_key="out-1",
            )
            await uow.outbox.add(message)
            assert await uow.outbox.count_pending(world.id) == 1
            assert [item.id for item in await uow.outbox.claim_due(10)] == [message.id]
            assert await uow.outbox.ack(message.id)
            run_id = new_phase_run_id()
            await uow.phases.create_run(PhaseRun(id=run_id, world_id=world.id, absolute_index=0))
            seen = WorldEvent(
                id=new_event_id(),
                world_id=world.id,
                sequence=1,
                event_type=EventType.WORLD_TICKED,
                absolute_index=0,
                phase_run_id=run_id,
            )
            await uow.events.append_event(seen)
            observation = Observation(
                id=new_observation_id(),
                world_id=world.id,
                event_id=seen.id,
                observer_character_id=character.id,
                facts=[ObservationFact(key="weather", value="cold")],
                created_phase_index=0,
            )
            await uow.perception.add_observation(observation)
            assert await uow.perception.observations_for_event(observation.event_id) == [
                observation
            ]
            memory = RecentMemory(
                id=new_memory_id(),
                world_id=world.id,
                owner_character_id=character.id,
                observation_id=observation.id,
                text="Cold dawn.",
                created_phase_index=0,
            )
            await uow.perception.add_memory(memory)
            assert await uow.perception.memories_for_owner(character.id) == [memory]
            await uow.commit()

    asyncio.run(_inner())


def test_rollback_discards_uncommitted_writes(migrated_db: None) -> None:
    async def _inner() -> None:
        world = _world()
        engine = create_engine(Settings())
        try:
            with pytest.raises(RuntimeError):
                async with create_unit_of_work(engine) as uow:
                    await uow.worlds.add(world)
                    raise RuntimeError("boom")
            async with create_unit_of_work(engine) as uow:
                with pytest.raises(DomainError) as excinfo:
                    await uow.worlds.get(world.id)
                assert excinfo.value.code is ErrorCode.NOT_FOUND
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_overlapping_writers_conflict(migrated_db: None) -> None:
    async def _inner() -> None:
        first_engine = create_engine(Settings())
        second_engine = create_engine(Settings())
        try:
            async with create_unit_of_work(first_engine) as first:
                world, place = await _seed_place(first)
                character = _character(world.id, place.id)
                await first.characters.add_identity(character.id, world.id, "Wren")
                await first.characters.add_card(
                    CharacterCard(id=uuid.uuid4(), character_id=character.id, name="W", version=1)
                )
                await first.characters.add_state(character)
                await first.commit()
            async with create_unit_of_work(first_engine) as reader_a:
                async with create_unit_of_work(second_engine) as reader_b:
                    stale_a = await reader_a.characters.get(character.id)
                    stale_b = await reader_b.characters.get(character.id)
                    await reader_a.characters.save_state(
                        stale_a.model_copy(update={"stamina": 10}), expected_version=0
                    )
                    await reader_a.commit()
                    with pytest.raises(DomainError) as excinfo:
                        await reader_b.characters.save_state(
                            stale_b.model_copy(update={"stamina": 20}), expected_version=0
                        )
                    assert excinfo.value.code is ErrorCode.VERSION_CONFLICT
        finally:
            await first_engine.dispose()
            await second_engine.dispose()

    asyncio.run(_inner())


def test_canonical_order_is_deterministic(migrated_db: None) -> None:
    ids = [uuid.uuid4() for _ in range(5)]
    assert canonical_order(ids + [ids[0]]) == sorted(ids, key=lambda item: item.hex)
