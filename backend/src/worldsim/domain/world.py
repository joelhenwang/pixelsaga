"""World, location, and route contracts (owned by S0-DOM-001).

Routes are nested value objects in Stage 0; the dedicated route table
arrives with Stage 2 persistence.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import PhaseName, WorldStatus
from worldsim.domain.ids import LocationId, RouteId, WorldId


class Route(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: RouteId
    destination_location_id: LocationId
    duration_phases: int = Field(ge=1)
    stamina_cost: int = Field(ge=0)


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: LocationId
    world_id: WorldId
    name: str = Field(min_length=1, max_length=128)
    region: str = Field(default="", max_length=128)
    capacity: int | None = Field(default=None, ge=1)
    routes: list[Route] = Field(default_factory=list)
    discovered: bool = False
    version: int = Field(default=0, ge=0)


class World(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: WorldId
    name: str = Field(min_length=1, max_length=128)
    status: WorldStatus = WorldStatus.ACTIVE
    day: int = Field(default=1, ge=1)
    phase: PhaseName = PhaseName.DAWN
    seed_version: str = Field(min_length=1, max_length=64)
    version: int = Field(default=0, ge=0)
