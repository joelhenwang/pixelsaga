"""Shared WorldView builder for engine rule tests (owned by S0-SIM-001)."""

from __future__ import annotations

from worldsim.domain.characters import Character
from worldsim.domain.enums import LifeStatus
from worldsim.domain.ids import (
    new_character_id,
    new_location_id,
    new_route_id,
    new_world_id,
)
from worldsim.domain.rules.views import WorldView
from worldsim.domain.world import Location, Route, World


def make_world_view(stamina: int = 80, mana: int = 40, dead: bool = False) -> WorldView:
    wid = new_world_id()
    home_id = new_location_id()
    market_id = new_location_id()
    route = Route(
        id=new_route_id(),
        destination_location_id=market_id,
        duration_phases=1,
        stamina_cost=10,
    )
    hearth = Location(id=home_id, world_id=wid, name="Hearth", routes=[route], capacity=2)
    market = Location(id=market_id, world_id=wid, name="Market", discovered=True)
    wren = Character(
        id=new_character_id(),
        world_id=wid,
        name="Wren",
        card_version=1,
        life_status=LifeStatus.DEAD if dead else LifeStatus.ALIVE,
        location_id=home_id,
        stamina=stamina,
        mana=mana,
    )
    ash = Character(
        id=new_character_id(),
        world_id=wid,
        name="Ash",
        card_version=1,
        location_id=market_id,
        stamina=70,
        mana=60,
    )
    return WorldView(
        world=World(id=wid, name="Vale", seed_version="s0-test"),
        characters=[wren, ash],
        locations=[hearth, market],
    )
