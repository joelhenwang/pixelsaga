"""Stage 0 action feasibility (owned by S0-SIM-001).

Checks answer whether an attempt may proceed; planning and projection
turn feasible attempts into effects and state.
"""

from __future__ import annotations

from worldsim.domain.characters import Character
from worldsim.domain.commands import (
    ActionIntent,
    MoveAction,
    ObserveAction,
    RestAction,
    WaitAction,
)
from worldsim.domain.enums import STAGE0_ACTION_FAMILIES, ActionFamily
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.rules.resources import spend
from worldsim.domain.rules.views import WorldView
from worldsim.domain.world import Location


def require_stage0_family(family: ActionFamily) -> None:
    if family not in STAGE0_ACTION_FAMILIES:
        raise DomainError(
            ErrorCode.UNSUPPORTED_ACTION,
            f"Stage 0 cannot resolve {family.value}",
            {"family": family.value},
        )


def require_alive(character: Character) -> None:
    if character.life_status.value != "alive":
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            "the character cannot act",
            {"character": str(character.id)},
        )


def check_wait(character: Character) -> None:
    require_alive(character)


def check_rest(character: Character, action: RestAction) -> None:
    require_alive(character)
    if action.duration_phases < 1:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "rest needs a duration")


def check_observe(character: Character, action: ObserveAction) -> None:
    require_alive(character)
    if not action.focus.strip():
        raise DomainError(ErrorCode.VALIDATION_FAILED, "observe needs a focus")


def check_move(
    character: Character,
    action: MoveAction,
    origin: Location,
    destination: Location,
    occupant_count: int = 0,
) -> None:
    require_alive(character)
    if action.destination_location_id != destination.id:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "destination mismatch")
    if action.route_id is None:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, "simple moves need a route")
    route = next((r for r in origin.routes if r.id == action.route_id), None)
    if route is None or route.destination_location_id != destination.id:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            "no route from here to the destination",
            {"destination": str(destination.id)},
        )
    spend(character.stamina, route.stamina_cost)
    if destination.capacity is not None and occupant_count >= destination.capacity:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            "the destination is full",
            {"destination": str(destination.id)},
        )


def check_intent(intent: ActionIntent, view: WorldView) -> None:
    """Dispatch one scripted intent to its feasibility check."""
    require_stage0_family(intent.family)
    character = view.character(intent.character_id)
    match intent:
        case MoveAction():
            origin = view.location(character.location_id)
            destination = view.location(intent.destination_location_id)
            check_move(
                character,
                intent,
                origin,
                destination,
                occupant_count=len(view.occupants(destination.id)),
            )
        case WaitAction():
            check_wait(character)
        case RestAction():
            check_rest(character, intent)
        case ObserveAction():
            check_observe(character, intent)
