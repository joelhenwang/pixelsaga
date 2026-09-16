"""Directional relationship contracts (owned by S2-REL-001).

Evidence is the canon; the projection is a fold. A→B and B→A are
independent rows: helping someone need not make them trust you.
Deltas clamp small, totals clamp at ±100, and every recording lands
beside its audit command in one transaction.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import RelationshipDimension
from worldsim.domain.ids import (
    CharacterId,
    EventId,
    RelationshipEvidenceId,
    RelationshipId,
    WorldId,
)

DIMENSION_MIN = -100
DIMENSION_MAX = 100
DELTA_MIN = -10
DELTA_MAX = 10


class RelationshipEvidence(BaseModel):
    """One sourced directional observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: RelationshipEvidenceId
    world_id: WorldId
    source_id: CharacterId
    target_id: CharacterId
    dimension: RelationshipDimension
    delta: int = Field(ge=DELTA_MIN, le=DELTA_MAX)
    note: str = Field(default="", max_length=512)
    source_event_id: EventId | None = None
    version: int = Field(default=0, ge=0)


class Relationship(BaseModel):
    """Folded directional standing from source toward target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: RelationshipId
    world_id: WorldId
    source_id: CharacterId
    target_id: CharacterId
    trust: int = Field(default=0, ge=DIMENSION_MIN, le=DIMENSION_MAX)
    affection: int = Field(default=0, ge=DIMENSION_MIN, le=DIMENSION_MAX)
    respect: int = Field(default=0, ge=DIMENSION_MIN, le=DIMENSION_MAX)
    version: int = Field(default=0, ge=0)


def fold(evidence: RelationshipEvidence, current: Relationship) -> Relationship:
    """Apply one evidence delta with clamped totals."""
    value = getattr(current, evidence.dimension.value) + evidence.delta
    clamped = max(DIMENSION_MIN, min(DIMENSION_MAX, value))
    return current.model_copy(update={evidence.dimension.value: clamped})


def describe(relationship: Relationship, target_name: str) -> str:
    """One-line standing for context and UI."""
    return (
        f"{target_name}: trust {relationship.trust}, "
        f"affection {relationship.affection}, respect {relationship.respect}"
    )
