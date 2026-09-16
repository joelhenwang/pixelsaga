"""D&D party roster contracts (owned by DND-WIRE).

One row per adventurer per world: the player's sheet plus recruited
companions. ``name_key`` is the slugified name and carries the
uniqueness that makes repeat RECRUIT tags idempotent. Sheet HP and
slots mutate through version-guarded saves; joins are inserts.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import FocusSlot
from worldsim.domain.ids import CharacterId, MonsterId, PartyMemberId, WorldId
from worldsim.domain.rules.dnd import Sheet, slugify


class PartyMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: PartyMemberId
    world_id: WorldId
    name: str = Field(min_length=1, max_length=128)
    name_key: str = Field(min_length=1, max_length=128)
    character_id: CharacterId | None = None
    focus_slot: FocusSlot = FocusSlot.COMPANION
    sheet: Sheet
    version: int = Field(default=0, ge=0)


def party_name_key(name: str) -> str:
    """Dedupe key for member names (monolith compares lowercased names)."""
    return slugify(name)


class Monster(BaseModel):
    """One persistent monster pool per world and name key.

    Narrator tags address monsters by name only, so one row tracks the
    live pool for a key. A new ENCOUNTER respawns the key to full: a
    fresh pack, not the survivors of the last fight.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: MonsterId
    world_id: WorldId
    name_key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    hp_current: int = Field(ge=0)
    hp_max: int = Field(ge=0)
    ac: int = Field(ge=0)
    version: int = Field(default=0, ge=0)
