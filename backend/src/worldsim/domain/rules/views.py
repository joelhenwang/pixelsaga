"""Shared rule input bundle (owned by S0-SIM-001)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from worldsim.domain.characters import Character
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import CharacterId, LocationId
from worldsim.domain.world import Location, World


class WorldView(BaseModel):
    """Everything a pure rule may read for one decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    world: World
    characters: list[Character] = []
    locations: list[Location] = []

    def character(self, character_id: CharacterId) -> Character:
        for candidate in self.characters:
            if candidate.id == character_id:
                return candidate
        raise DomainError(ErrorCode.NOT_FOUND, f"unknown character: {character_id}")

    def location(self, location_id: LocationId) -> Location:
        for candidate in self.locations:
            if candidate.id == location_id:
                return candidate
        raise DomainError(ErrorCode.NOT_FOUND, f"unknown location: {location_id}")

    def occupants(self, location_id: LocationId) -> list[Character]:
        return [c for c in self.characters if c.location_id == location_id]
