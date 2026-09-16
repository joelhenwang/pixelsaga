"""Deterministic feasibility envelopes (owned by S1-RESOLVE-001).

Pure rules over one intent and the live view. Each envelope says whether
the outcome is already determined (no model call needed) or genuinely
ambiguous. Stale aggregates fail deterministically: the sealed snapshot
versions travel with the request and any touched character whose live
version moved on means the intent planned against old world state.

Stage 1 permits only effects the current rules can already plan or the
model may propose inside the feasible set: movement, observation and
disclosure, wait/rest, and bounded resource changes.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.commands import CommunicateAction
from worldsim.domain.effects import DomainEffect
from worldsim.domain.enums import EffectType, ResolutionOutcome
from worldsim.domain.errors import DomainError
from worldsim.domain.ids import CharacterId, IntentId
from worldsim.domain.resolution import AmbiguityPacket
from worldsim.domain.rules.actions import check_communicate, check_intent
from worldsim.domain.rules.scenes import mutable_aggregates
from worldsim.domain.rules.validation import plan_effects
from worldsim.domain.rules.views import WorldView
from worldsim.domain.scenes import Intent

#: Effect types a Stage 1 resolution may carry (no clock, no generic sets).
STAGE1_FEASIBLE_EFFECTS = frozenset(
    {
        EffectType.MOVE_ENTITY,
        EffectType.RECORD_OBSERVATION,
        EffectType.RECORD_MEMORY,
        EffectType.RESOURCE_ADJUSTED,
    }
)

_OUTCOME_RANK = {
    ResolutionOutcome.SUCCESS: 0,
    ResolutionOutcome.PARTIAL: 1,
    ResolutionOutcome.FAILURE: 2,
    ResolutionOutcome.IMPOSSIBLE: 3,
}


class FeasibilityEnvelope(BaseModel):
    """One intent's deterministic resolution boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent_id: IntentId
    author_character_id: CharacterId
    determined: bool
    outcome: ResolutionOutcome | None = None
    candidate_effects: list[DomainEffect] = Field(default_factory=list)
    allowed_outcomes: list[ResolutionOutcome] = Field(default_factory=list)
    allowed_aggregate_ids: list[str] = Field(default_factory=list)
    reason: str = Field(default="", max_length=512)


def _character_aggregates(intent: Intent) -> list[str]:
    return sorted(a for a in mutable_aggregates(intent) if a.startswith("character:"))


def build_envelope(
    intent: Intent,
    view: WorldView,
    expected_versions: dict[str, int],
) -> FeasibilityEnvelope:
    """Deterministic envelope: stale, impossible, determined, or ambiguous."""
    aggregates = _character_aggregates(intent)
    for aggregate in aggregates:
        character_id = uuid.UUID(aggregate.split(":", 1)[1])
        live = view.character(character_id).version
        if expected_versions.get(aggregate) != live:
            return FeasibilityEnvelope(
                intent_id=intent.id,
                author_character_id=intent.author_character_id,
                determined=True,
                outcome=ResolutionOutcome.FAILURE,
                allowed_outcomes=[ResolutionOutcome.FAILURE],
                allowed_aggregate_ids=aggregates,
                reason=f"stale aggregate: {aggregate}",
            )
    try:
        if isinstance(intent.action, CommunicateAction):
            check_communicate(view.character(intent.action.character_id), intent.action)
        else:
            check_intent(intent.action, view)
    except DomainError as exc:
        return FeasibilityEnvelope(
            intent_id=intent.id,
            author_character_id=intent.author_character_id,
            determined=True,
            outcome=ResolutionOutcome.IMPOSSIBLE,
            allowed_outcomes=[ResolutionOutcome.IMPOSSIBLE],
            allowed_aggregate_ids=aggregates,
            reason=f"infeasible: {exc}",
        )
    if isinstance(intent.action, CommunicateAction):
        return FeasibilityEnvelope(
            intent_id=intent.id,
            author_character_id=intent.author_character_id,
            determined=False,
            allowed_outcomes=[
                ResolutionOutcome.SUCCESS,
                ResolutionOutcome.PARTIAL,
                ResolutionOutcome.FAILURE,
            ],
            allowed_aggregate_ids=sorted(
                set(aggregates) | {f"character:{intent.action.target_character_id}"}
            ),
            reason="dialogue outcome needs the resolver",
        )
    try:
        effects = plan_effects(intent.action, view)
    except DomainError as exc:
        return FeasibilityEnvelope(
            intent_id=intent.id,
            author_character_id=intent.author_character_id,
            determined=True,
            outcome=ResolutionOutcome.FAILURE,
            allowed_outcomes=[ResolutionOutcome.FAILURE],
            allowed_aggregate_ids=aggregates,
            reason=f"planning failed: {exc}",
        )
    return FeasibilityEnvelope(
        intent_id=intent.id,
        author_character_id=intent.author_character_id,
        determined=True,
        outcome=ResolutionOutcome.SUCCESS,
        candidate_effects=effects,
        allowed_outcomes=[ResolutionOutcome.SUCCESS],
        allowed_aggregate_ids=aggregates,
        reason="deterministic",
    )


def merge_determined(
    envelopes: list[FeasibilityEnvelope],
) -> tuple[ResolutionOutcome, list[DomainEffect]]:
    """Worst-outcome merge of determined envelopes plus all their effects."""
    outcome = ResolutionOutcome.SUCCESS
    effects: list[DomainEffect] = []
    for envelope in envelopes:
        assert envelope.determined and envelope.outcome is not None
        if _OUTCOME_RANK[envelope.outcome] > _OUTCOME_RANK[outcome]:
            outcome = envelope.outcome
        effects.extend(envelope.candidate_effects)
    return outcome, effects


def build_packet(
    *,
    scene_id: uuid.UUID,
    world_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    intents: list[Intent],
    envelopes: list[FeasibilityEnvelope],
) -> AmbiguityPacket:
    """Bounded ambiguity packet for the resolver model."""
    allowed: list[ResolutionOutcome] = []
    for envelope in envelopes:
        for outcome in envelope.allowed_outcomes:
            if outcome not in allowed:
                allowed.append(outcome)
    aggregates: list[str] = []
    for envelope in envelopes:
        for aggregate in envelope.allowed_aggregate_ids:
            if aggregate not in aggregates:
                aggregates.append(aggregate)
    determined: list[DomainEffect] = []
    for envelope in envelopes:
        determined.extend(envelope.candidate_effects)
    summaries = [
        f"{intent.action.family.value} by {intent.author_character_id}"
        for intent in sorted(intents, key=lambda i: str(i.id))
    ]
    return AmbiguityPacket(
        scene_id=scene_id,
        world_id=world_id,
        snapshot_id=snapshot_id,
        intent_ids=sorted((i.id for i in intents), key=str),
        summaries=summaries,
        allowed_outcomes=allowed,
        allowed_aggregate_ids=sorted(aggregates),
        determined_effects=determined,
        reason="scene needs model-assisted resolution",
    )


def resolution_seed(scene_id: uuid.UUID, snapshot_id: uuid.UUID) -> int:
    """Deterministic seed evidence for a scene resolution (no draws yet)."""
    digest = uuid.uuid5(uuid.NAMESPACE_OID, f"resolve:{scene_id}:{snapshot_id}").bytes
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


__all__ = [
    "STAGE1_FEASIBLE_EFFECTS",
    "FeasibilityEnvelope",
    "build_envelope",
    "build_packet",
    "merge_determined",
    "resolution_seed",
]
