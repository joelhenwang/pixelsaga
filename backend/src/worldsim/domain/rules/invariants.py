"""Hard-invariant audits over a world view (owned by S0-SIM-001)."""

from __future__ import annotations

from collections.abc import Callable

from worldsim.domain.rules.views import WorldView

Check = Callable[[WorldView], list[str]]


def _resources_in_bounds(view: WorldView) -> list[str]:
    breaches: list[str] = []
    for character in view.characters:
        for resource, value in (("stamina", character.stamina), ("mana", character.mana)):
            if not 0 <= value <= 100:
                breaches.append(f"{character.id} {resource}={value}")
    return breaches


def _locations_known(view: WorldView) -> list[str]:
    known = {location.id for location in view.locations}
    breaches: list[str] = []
    for character in view.characters:
        if character.location_id not in known:
            breaches.append(f"{character.id} at unknown {character.location_id}")
    for location in view.locations:
        for route in location.routes:
            if route.destination_location_id not in known:
                breaches.append(f"{location.id} route to unknown {route.destination_location_id}")
    return breaches


def _world_membership(view: WorldView) -> list[str]:
    breaches: list[str] = []
    for character in view.characters:
        if character.world_id != view.world.id:
            breaches.append(f"{character.id} outside world")
    for location in view.locations:
        if location.world_id != view.world.id:
            breaches.append(f"{location.id} outside world")
    return breaches


INVARIANTS: dict[str, Check] = {
    "resources_in_bounds": _resources_in_bounds,
    "locations_known": _locations_known,
    "world_membership": _world_membership,
}


def violations(view: WorldView) -> dict[str, list[str]]:
    """Run every registered check; empty lists mean the invariant holds."""
    return {name: check(view) for name, check in INVARIANTS.items()}
