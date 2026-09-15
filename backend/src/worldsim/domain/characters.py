"""Character card and dynamic-state contracts (owned by S0-DOM-001).

The card owns stable identity; state owns mutable projections. Memories
live in perception records and are only referenced by owner here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import LifeStatus
from worldsim.domain.ids import CardId, CharacterId, LocationId, WorldId

ConditionCode = str


class CharacterCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: CardId
    character_id: CharacterId
    name: str = Field(min_length=1, max_length=128)
    appearance: str = Field(default="", max_length=2000)
    personality: str = Field(default="", max_length=2000)
    background: str = Field(default="", max_length=2000)
    version: int = Field(default=1, ge=1)


class Character(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: CharacterId
    world_id: WorldId
    name: str = Field(min_length=1, max_length=128)
    card_version: int = Field(ge=1)
    life_status: LifeStatus = LifeStatus.ALIVE
    location_id: LocationId
    stamina: int = Field(ge=0, le=100)
    mana: int = Field(ge=0, le=100)
    conditions: list[ConditionCode] = Field(default_factory=list, max_length=8)
    version: int = Field(default=0, ge=0)
