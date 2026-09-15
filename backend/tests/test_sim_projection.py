import pytest
from helpers_sim import make_world_view

from worldsim.domain.commands import MoveAction, RestAction
from worldsim.domain.effects import ResourceAdjustedEffect
from worldsim.domain.enums import ResourceKind
from worldsim.domain.errors import DomainError
from worldsim.domain.ids import new_snapshot_id
from worldsim.domain.rules.projection import apply_character_effect, apply_world_effect
from worldsim.domain.rules.validation import plan_effects


def test_rest_plans_recovery_and_projects_with_cap() -> None:
    view = make_world_view(stamina=80, mana=38)
    wren = view.characters[0]
    intent = RestAction(character_id=wren.id, snapshot_id=new_snapshot_id(), duration_phases=2)
    effects = plan_effects(intent, view)
    assert len(effects) == 2
    rested = wren
    for effect in effects:
        rested = apply_character_effect(rested, effect)
    assert (rested.stamina, rested.mana) == (100, 48)
    assert rested.version == wren.version + 2


def test_full_rest_plans_nothing() -> None:
    view = make_world_view(stamina=100, mana=100)
    wren = view.characters[0]
    assert plan_effects(RestAction(character_id=wren.id, snapshot_id=new_snapshot_id()), view) == []


def test_move_plans_relocation_plus_cost() -> None:
    view = make_world_view()
    wren = view.characters[0]
    market = view.locations[1]
    route = view.locations[0].routes[0]
    effects = plan_effects(
        MoveAction(
            character_id=wren.id,
            snapshot_id=new_snapshot_id(),
            destination_location_id=market.id,
            route_id=route.id,
        ),
        view,
    )
    assert len(effects) == 2
    moved = wren
    for effect in effects:
        moved = apply_character_effect(moved, effect)
    assert moved.location_id == market.id
    assert moved.stamina == 70
    assert moved.version == wren.version + 2


def test_overspend_projection_raises() -> None:
    view = make_world_view()
    wren = view.characters[0]
    effect = ResourceAdjustedEffect(
        affected_ids=[wren.id],
        expected_versions={str(wren.id): wren.version},
        resource=ResourceKind.STAMINA,
        delta=-200,
    )
    with pytest.raises(DomainError, match="bounds"):
        apply_character_effect(wren, effect)


def test_repeated_projection_is_deterministic() -> None:
    view = make_world_view()
    wren = view.characters[0]
    market = view.locations[1]
    route = view.locations[0].routes[0]
    effects = plan_effects(
        MoveAction(
            character_id=wren.id,
            snapshot_id=new_snapshot_id(),
            destination_location_id=market.id,
            route_id=route.id,
        ),
        view,
    )
    first = wren
    for effect in effects:
        first = apply_character_effect(first, effect)
    for _ in range(50):
        replay = wren
        for effect in effects:
            replay = apply_character_effect(replay, effect)
        assert replay == first


def test_world_tick_projects_calendar() -> None:
    from worldsim.domain.effects import AdvanceClockEffect

    view = make_world_view()
    ticked = apply_world_effect(
        view.world,
        AdvanceClockEffect(
            affected_ids=[view.world.id],
            expected_versions={str(view.world.id): view.world.version},
            from_index=0,
            to_index=9,
        ),
    )
    assert (ticked.day, ticked.phase.value) == (1, "midnight")
    assert ticked.version == view.world.version + 1
