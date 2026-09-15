import pytest
from pydantic import TypeAdapter, ValidationError

from worldsim.domain.effects import (
    AdvanceClockEffect,
    DomainEffect,
    MoveEntityEffect,
    ResourceAdjustedEffect,
)
from worldsim.domain.enums import EffectType, EventType, ResourceKind
from worldsim.domain.events import CommittedEffect, WorldEvent, WorldEventRecord
from worldsim.domain.ids import (
    new_character_id,
    new_event_id,
    new_location_id,
    new_phase_run_id,
    new_world_id,
)


def _versions(target_id: object) -> dict[str, int]:
    return {str(target_id): 3}


def test_effect_union_dispatches_and_round_trips() -> None:
    adapter: TypeAdapter[DomainEffect] = TypeAdapter(DomainEffect)
    character_id = new_character_id()
    effect = adapter.validate_python(
        {
            "effect_type": "resource_adjusted",
            "affected_ids": [str(character_id)],
            "expected_versions": _versions(character_id),
            "resource": "stamina",
            "delta": -15,
        }
    )
    assert isinstance(effect, ResourceAdjustedEffect)
    assert effect.resource is ResourceKind.STAMINA
    assert effect.effect_type is EffectType.RESOURCE_ADJUSTED
    assert adapter.validate_json(effect.model_dump_json()) == effect


def test_effect_rejects_uncovered_targets_zero_delta_and_stalled_clock() -> None:
    character_id = new_character_id()
    with pytest.raises(ValidationError, match="must cover every affected"):
        ResourceAdjustedEffect(
            affected_ids=[character_id],
            expected_versions={},
            resource=ResourceKind.MANA,
            delta=5,
        )
    with pytest.raises(ValidationError):
        ResourceAdjustedEffect(
            affected_ids=[character_id],
            expected_versions=_versions(character_id),
            resource=ResourceKind.MANA,
            delta=0,
        )
    world_id = new_world_id()
    with pytest.raises(ValidationError, match="forward"):
        AdvanceClockEffect(
            affected_ids=[world_id],
            expected_versions=_versions(world_id),
            from_index=7,
            to_index=7,
        )
    with pytest.raises(ValidationError, match="change location"):
        place = new_location_id()
        MoveEntityEffect(
            affected_ids=[character_id],
            expected_versions=_versions(character_id),
            from_location_id=place,
            to_location_id=place,
        )


def test_event_record_requires_contiguous_ordinals() -> None:
    event_id = new_event_id()
    event = WorldEvent(
        id=event_id,
        world_id=new_world_id(),
        sequence=1,
        event_type=EventType.ACTION_RESOLVED,
        absolute_index=4,
        phase_run_id=new_phase_run_id(),
    )
    character_id = new_character_id()
    first = CommittedEffect(
        event_id=event_id,
        ordinal=0,
        effect=ResourceAdjustedEffect(
            affected_ids=[character_id],
            expected_versions=_versions(character_id),
            resource=ResourceKind.STAMINA,
            delta=-5,
        ),
    )
    record = WorldEventRecord(event=event, effects=[first])
    assert record.model_validate_json(record.model_dump_json()) == record
    second = CommittedEffect(event_id=event_id, ordinal=2, effect=first.effect)
    with pytest.raises(ValidationError, match="contiguous"):
        WorldEventRecord(event=event, effects=[first, second])
    with pytest.raises(ValidationError, match="sequence"):
        WorldEvent(
            id=event_id,
            world_id=new_world_id(),
            sequence=0,
            event_type=EventType.WORLD_TICKED,
            absolute_index=0,
            phase_run_id=new_phase_run_id(),
        )
