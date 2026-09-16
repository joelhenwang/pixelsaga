"""Skill, item, and training-progress contracts (owned by S2-PROGRESS-001).

Progress is evidence-counted: each distinct training session adds a
diminishing gain toward the skill cap, and the same session key can
never award twice. Item definitions are content (see
`content/definitions/items.json`); instances carry the single owner
that makes one item belong to one holder.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.ids import (
    CharacterId,
    ItemInstanceId,
    SkillId,
    WorldId,
)

#: Progress cap per skill.
SKILL_CAP = 100
#: Sessions counted with diminishing gains: 8, 7, ... floored at 1.
FIRST_SESSION_GAIN = 8
#: Stamina price of one training session.
TRAINING_STAMINA_COST = 10


class SkillDefinition(BaseModel):
    """One trainable skill, registered lazily on first session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: SkillId
    world_id: WorldId
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    max_progress: int = Field(default=SKILL_CAP, ge=1)
    version: int = Field(default=0, ge=0)


class CharacterSkill(BaseModel):
    """Folded progress of one character in one skill."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: SkillId
    world_id: WorldId
    character_id: CharacterId
    skill_key: str = Field(min_length=1, max_length=64)
    progress: int = Field(default=0, ge=0)
    sessions: int = Field(default=0, ge=0)
    version: int = Field(default=0, ge=0)


class TrainingSession(BaseModel):
    """One counted session: the duplicate-proof progress record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: SkillId
    world_id: WorldId
    character_id: CharacterId
    skill_key: str = Field(min_length=1, max_length=64)
    session_key: str = Field(min_length=1, max_length=128)
    gain: int = Field(ge=0)
    version: int = Field(default=0, ge=0)


class ItemInstance(BaseModel):
    """One item stack with exactly one holder (or none, lying where left)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ItemInstanceId
    world_id: WorldId
    item_key: str = Field(min_length=1, max_length=64)
    owner_id: CharacterId | None = None
    quantity: int = Field(default=1, ge=1)
    version: int = Field(default=0, ge=0)


def session_gain(sessions_awarded: int) -> int:
    """Diminishing gain for the next session: 8, 7, ..., floored at 1."""
    return max(1, FIRST_SESSION_GAIN - sessions_awarded)


def fold_progress(current: int, gain: int, cap: int = SKILL_CAP) -> int:
    """Clamp folded progress at the skill cap."""
    return min(cap, current + gain)
