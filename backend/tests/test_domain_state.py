import pytest
from pydantic import ValidationError

from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.enums import LifeStatus, OutboxState, TaskRunState, Visibility, WorldStatus
from worldsim.domain.ids import (
    new_card_id,
    new_character_id,
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
from worldsim.domain.tasks import OutboxMessage, TaskRun
from worldsim.domain.world import Location, World


def test_world_character_state_round_trip() -> None:
    world_id = new_world_id()
    home = new_location_id()
    world = World(id=world_id, name="Ember Vale", seed_version="s0-001")
    assert world.status is WorldStatus.ACTIVE
    assert world.model_validate_json(world.model_dump_json()) == world
    character_id = new_character_id()
    character = Character(
        id=character_id,
        world_id=world_id,
        name="Wren",
        card_version=1,
        location_id=home,
        stamina=80,
        mana=40,
    )
    assert character.life_status is LifeStatus.ALIVE
    assert character.model_validate_json(character.model_dump_json()) == character
    card = CharacterCard(id=new_card_id(), character_id=character_id, name="Wren")
    assert card.version == 1
    place = Location(id=home, world_id=world_id, name="Hearth")
    assert place.version == 0


def test_state_enforces_bounds_and_immutability() -> None:
    world_id = new_world_id()
    home = new_location_id()
    with pytest.raises(ValidationError):
        Character(
            id=new_character_id(),
            world_id=world_id,
            name="Wren",
            card_version=1,
            location_id=home,
            stamina=-1,
            mana=101,
        )
    character = Character(
        id=new_character_id(),
        world_id=world_id,
        name="Wren",
        card_version=1,
        location_id=home,
        stamina=50,
        mana=50,
    )
    with pytest.raises(ValidationError):
        character.stamina = 10  # type: ignore[misc]


def test_snapshot_tasks_and_perception_contracts() -> None:
    world_id = new_world_id()
    character_id = new_character_id()
    snapshot = PhaseSnapshot(
        id=new_snapshot_id(),
        world_id=world_id,
        phase_run_id=new_phase_run_id(),
        absolute_index=0,
        world_version=0,
        characters=[SnapshotCharacter(character_id=character_id, version=0)],
        content_hash="0" * 64,
    )
    assert snapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
    with pytest.raises(ValidationError):
        PhaseSnapshot(
            id=new_snapshot_id(),
            world_id=world_id,
            phase_run_id=new_phase_run_id(),
            absolute_index=0,
            world_version=0,
            characters=[],
            content_hash="not-a-hash",
        )
    run = PhaseRun(id=new_phase_run_id(), world_id=world_id, absolute_index=0)
    assert run.state.value == "created"
    task = TaskRun(id=new_task_id(), world_id=world_id, kind="phase_advance")
    assert task.state is TaskRunState.PENDING
    message = OutboxMessage(
        id=new_outbox_id(), world_id=world_id, kind="phase_followup", idempotency_key="out-1"
    )
    assert message.state is OutboxState.PENDING
    event_id = new_event_id()
    observation = Observation(
        id=new_observation_id(),
        world_id=world_id,
        event_id=event_id,
        observer_character_id=character_id,
        facts=[ObservationFact(key="weather", value="cold dawn")],
        created_phase_index=0,
    )
    memory = RecentMemory(
        id=new_memory_id(),
        world_id=world_id,
        owner_character_id=character_id,
        observation_id=observation.id,
        text="Cold dawn at the hearth.",
        created_phase_index=0,
    )
    assert memory.visibility is Visibility.PRIVATE
    assert memory.model_validate_json(memory.model_dump_json()) == memory
