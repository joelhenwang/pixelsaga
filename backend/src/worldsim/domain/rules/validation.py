"""Feasible intent to candidate effects (owned by S0-SIM-001).

WAIT changes nothing and shares the phase tick event. Every other family
produces the typed effects the canonical transaction revalidates.
"""

from __future__ import annotations

from worldsim.domain.characters import Character
from worldsim.domain.commands import (
    ActionIntent,
    AppealAction,
    MoveAction,
    ObserveAction,
    RestAction,
    SparAction,
    TransferAction,
    WaitAction,
)
from worldsim.domain.effects import (
    DomainEffect,
    MemoryRecordedEffect,
    MoveEntityEffect,
    ObservationRecordedEffect,
    ResourceAdjustedEffect,
)
from worldsim.domain.enums import ResourceKind
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.perception import ObservationFact
from worldsim.domain.rules.actions import check_intent
from worldsim.domain.rules.resources import rest_recovery, restore
from worldsim.domain.rules.views import WorldView


def plan_effects(intent: ActionIntent, view: WorldView) -> list[DomainEffect]:
    check_intent(intent, view)
    character = view.character(intent.character_id)
    affected = [character.id]
    versions = {str(character.id): character.version}
    match intent:
        case MoveAction():
            origin = view.location(character.location_id)
            route = next(r for r in origin.routes if r.id == intent.route_id)
            planned: list[DomainEffect] = [
                MoveEntityEffect(
                    affected_ids=affected,
                    expected_versions=versions,
                    from_location_id=origin.id,
                    to_location_id=intent.destination_location_id,
                    route_id=route.id,
                )
            ]
            if route.stamina_cost > 0:
                planned.append(
                    ResourceAdjustedEffect(
                        affected_ids=affected,
                        expected_versions=versions,
                        resource=ResourceKind.STAMINA,
                        delta=-route.stamina_cost,
                    )
                )
            return planned
        case WaitAction():
            return []
        case RestAction():
            stamina_gain, mana_gain = rest_recovery(intent.duration_phases)
            effects: list[DomainEffect] = []
            if restore(character.stamina, stamina_gain) > character.stamina:
                effects.append(
                    ResourceAdjustedEffect(
                        affected_ids=affected,
                        expected_versions=versions,
                        resource=ResourceKind.STAMINA,
                        delta=restore(character.stamina, stamina_gain) - character.stamina,
                    )
                )
            if restore(character.mana, mana_gain) > character.mana:
                effects.append(
                    ResourceAdjustedEffect(
                        affected_ids=affected,
                        expected_versions=versions,
                        resource=ResourceKind.MANA,
                        delta=restore(character.mana, mana_gain) - character.mana,
                    )
                )
            return effects
        case SparAction() | AppealAction() | TransferAction():
            # Outcomes settle post-commit from live rows, not from planned
            # effects; the empty plan keeps the envelope determined.
            return []
        case ObserveAction():
            return [
                ObservationRecordedEffect(
                    affected_ids=affected,
                    expected_versions=versions,
                    observer_character_id=character.id,
                    facts=[ObservationFact(key="focus", value=intent.focus)],
                )
            ]
        case _:
            raise DomainError(
                ErrorCode.UNSUPPORTED_ACTION,
                f"no effect plan for {intent.family.value}",
            )


def plan_memory(owner: Character, text: str) -> MemoryRecordedEffect:
    """Build a well-formed memory effect for a known owner version."""
    return MemoryRecordedEffect(
        affected_ids=[owner.id],
        expected_versions={str(owner.id): owner.version},
        owner_character_id=owner.id,
        text=text,
    )
