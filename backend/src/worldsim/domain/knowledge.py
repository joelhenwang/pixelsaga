"""Claim and belief contracts (owned by S2-KNOW-001).

Claims are propositions somebody voiced; beliefs are what listeners
carry. A false claim changes no objective row: it only folds into
listener beliefs with provenance. Contradiction is explicit (a
claim refuting another), repetition reinforces up to a cap, and
nothing is ever deleted: stale beliefs decay toward doubt, and
`effective_confidence` is the Stage 3 retrieval input.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.ids import (
    BeliefId,
    CharacterId,
    ClaimId,
    EventId,
    LocationId,
    WorldId,
)

#: Hearing a claim cold sets this confidence.
FIRST_HEARING = 0.5
#: The speaker stands behind their own words at this level.
SPEAKER_HOLD = 0.9
#: Repeat hearings add this much, up to the cap.
REINFORCE_STEP = 0.15
REINFORCE_CAP = 0.9
#: Contradicted and ancient beliefs rest here, never at zero.
DOUBT_FLOOR = 0.1
#: Linear decay per phase toward the floor when untouched.
DECAY_PER_PHASE = 0.01


class Claim(BaseModel):
    """One voiced proposition with its audience."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ClaimId
    world_id: WorldId
    speaker_id: CharacterId
    audience_location_id: LocationId | None = None
    proposition: str = Field(min_length=1, max_length=1024)
    refutes_claim_id: ClaimId | None = None
    source_event_id: EventId | None = None
    version: int = Field(default=0, ge=0)


class Belief(BaseModel):
    """One holder's confidence in a proposition, with provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: BeliefId
    world_id: WorldId
    holder_id: CharacterId
    proposition: str = Field(min_length=1, max_length=1024)
    confidence: float = Field(ge=0.0, le=1.0)
    source_claim_id: ClaimId | None = None
    last_touched_absolute: int = Field(ge=0)
    version: int = Field(default=0, ge=0)


def normalize(proposition: str) -> str:
    """Proposition identity: stripped, single-spaced, lowered."""
    return " ".join(proposition.strip().lower().split())


def reinforce(current: float) -> float:
    """Repeat hearing: step up toward the cap."""
    return min(REINFORCE_CAP, current + REINFORCE_STEP)


def contradict(current: float) -> float:
    """Explicit refutation: halve toward the doubt floor."""
    return max(DOUBT_FLOOR, current / 2.0)


def effective_confidence(belief: Belief, absolute: int) -> float:
    """Stored confidence decayed by untouched phases, floored at doubt."""
    age = max(0, absolute - belief.last_touched_absolute)
    return max(DOUBT_FLOOR, belief.confidence - DECAY_PER_PHASE * age)
