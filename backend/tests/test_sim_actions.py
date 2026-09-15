import pytest
from helpers_sim import make_world_view
from pydantic import ValidationError

from worldsim.domain.commands import (
    MoveAction,
    ObserveAction,
    RestAction,
    WaitAction,
)
from worldsim.domain.enums import ActionFamily
from worldsim.domain.errors import DomainError
from worldsim.domain.ids import new_route_id, new_snapshot_id
from worldsim.domain.rules.actions import check_intent, require_stage0_family
from worldsim.domain.rules.views import WorldView
from worldsim.domain.world import Location


def test_wait_rest_observe_feasible_when_alive() -> None:
    view = make_world_view()
    wren = view.characters[0]
    snapshot = new_snapshot_id()
    check_intent(WaitAction(character_id=wren.id, snapshot_id=snapshot), view)
    check_intent(RestAction(character_id=wren.id, snapshot_id=snapshot, duration_phases=2), view)
    check_intent(
        ObserveAction(character_id=wren.id, snapshot_id=snapshot, focus="the door"),
        view,
    )


def test_dead_characters_cannot_act() -> None:
    view = make_world_view(dead=True)
    wren = view.characters[0]
    snapshot = new_snapshot_id()
    with pytest.raises(DomainError, match="cannot act"):
        check_intent(WaitAction(character_id=wren.id, snapshot_id=snapshot), view)


def test_observe_needs_a_focus() -> None:
    view = make_world_view()
    wren = view.characters[0]
    snapshot = new_snapshot_id()
    with pytest.raises(DomainError, match="focus"):
        check_intent(
            ObserveAction(character_id=wren.id, snapshot_id=snapshot, focus="  "),
            view,
        )


def test_rest_rejects_empty_duration_at_parse() -> None:
    view = make_world_view()
    wren = view.characters[0]
    snapshot = new_snapshot_id()
    with pytest.raises(ValidationError):
        RestAction(character_id=wren.id, snapshot_id=snapshot, duration_phases=0)


def test_move_needs_route_stamina_and_space() -> None:
    view = make_world_view()
    wren = view.characters[0]
    market = view.locations[1]
    route = view.locations[0].routes[0]
    snapshot = new_snapshot_id()
    check_intent(
        MoveAction(
            character_id=wren.id,
            snapshot_id=snapshot,
            destination_location_id=market.id,
            route_id=route.id,
        ),
        view,
    )
    with pytest.raises(DomainError, match="need a route"):
        check_intent(
            MoveAction(
                character_id=wren.id,
                snapshot_id=snapshot,
                destination_location_id=market.id,
            ),
            view,
        )
    with pytest.raises(DomainError, match="no route"):
        check_intent(
            MoveAction(
                character_id=wren.id,
                snapshot_id=snapshot,
                destination_location_id=market.id,
                route_id=new_route_id(),
            ),
            view,
        )


def test_move_fails_when_exhausted_or_full() -> None:
    tired = make_world_view(stamina=5)
    wren = tired.characters[0]
    market = tired.locations[1]
    route = tired.locations[0].routes[0]
    snapshot = new_snapshot_id()
    with pytest.raises(DomainError, match="insufficient"):
        check_intent(
            MoveAction(
                character_id=wren.id,
                snapshot_id=snapshot,
                destination_location_id=market.id,
                route_id=route.id,
            ),
            tired,
        )
    view = make_world_view()
    home_route = view.locations[0].routes[0]
    full_market = Location(
        id=view.locations[1].id,
        world_id=view.world.id,
        name="Market",
        capacity=1,
        discovered=True,
    )
    full = WorldView(
        world=view.world,
        characters=view.characters,
        locations=[view.locations[0], full_market],
    )
    with pytest.raises(DomainError, match="full"):
        check_intent(
            MoveAction(
                character_id=view.characters[0].id,
                snapshot_id=snapshot,
                destination_location_id=full_market.id,
                route_id=home_route.id,
            ),
            full,
        )


def test_later_families_rejected_in_stage_zero() -> None:
    with pytest.raises(DomainError, match="Stage 0"):
        require_stage0_family(ActionFamily.ATTACK)
    require_stage0_family(ActionFamily.MOVE)
