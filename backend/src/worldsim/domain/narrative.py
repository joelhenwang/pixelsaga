"""Narrative hook and arc contracts (owned by S2-DIRECTOR-001).

Hooks are situational opportunities; arcs are longer purposes.
Both are director knowledge: they create openings, never outcomes.
Characters learn of them only through scenes, never through context.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import NarrativeStatus
from worldsim.domain.ids import ArcId, CharacterId, HookId, WorldId


class NarrativeHook(BaseModel):
    """One situational opening with explicit requested powers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: HookId
    world_id: WorldId
    title: str = Field(min_length=1, max_length=128)
    purpose: str = Field(default="", max_length=1024)
    requested_powers: list[str] = Field(default_factory=list)
    participant_ids: list[CharacterId] = Field(default_factory=list)
    status: NarrativeStatus = NarrativeStatus.PROPOSED
    version: int = Field(default=0, ge=0)


class NarrativeArc(BaseModel):
    """One longer purpose spanning several phases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ArcId
    world_id: WorldId
    title: str = Field(min_length=1, max_length=128)
    purpose: str = Field(default="", max_length=1024)
    status: NarrativeStatus = NarrativeStatus.PROPOSED
    version: int = Field(default=0, ge=0)
