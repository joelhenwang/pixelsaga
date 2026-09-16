"""Resolver proposal and ambiguity contracts (owned by S1-RESOLVE-001).

The model proposes a ``ResolverProposal`` (outcome plus typed effects);
the graph wraps an accepted proposal in a ``Resolution`` with deterministic
seed evidence. The model never mints IDs and never sees canon versions.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.effects import DomainEffect
from worldsim.domain.enums import ResolutionOutcome
from worldsim.domain.ids import IntentId, SceneId, SnapshotId, WorldId


class ResolverProposal(BaseModel):
    """Structured resolver output: outcome, feasible effects, rationale."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: ResolutionOutcome
    effects: list[DomainEffect] = Field(default_factory=list)
    rationale: str = Field(min_length=1, max_length=2000)


class AmbiguityPacket(BaseModel):
    """Bounded question for the resolver model (never canon, never stored)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_id: SceneId
    world_id: WorldId
    snapshot_id: SnapshotId
    intent_ids: list[IntentId] = Field(min_length=1)
    summaries: list[str] = Field(min_length=1, max_length=16)
    allowed_outcomes: list[ResolutionOutcome] = Field(min_length=1)
    allowed_aggregate_ids: list[str] = Field(default_factory=list)
    determined_effects: list[DomainEffect] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=512)
