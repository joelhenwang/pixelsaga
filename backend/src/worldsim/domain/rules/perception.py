"""Observer eligibility and permitted fact sets (owned by S1-PERCEPT-001).

Pure rules over ``ObservableEvent``. Eligibility, in order:

1. an explicitly disclosed fact reaches its recipients anywhere;
2. a concealed fact reaches nobody except disclosure recipients;
3. a participant perceives every non-concealed fact;
4. a character at the event location perceives public and scene facts;
5. anyone elsewhere perceives nothing.

Optional phrasing selects from the permitted set; it cannot add a
forbidden fact. Phrasing a key outside the permitted set fails loudly.
"""

from __future__ import annotations

from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import CharacterId, LocationId
from worldsim.domain.perception import FactVisibility, ObservableEvent, PerceivedFact


def is_eligible(
    event: ObservableEvent,
    observer_id: CharacterId,
    observer_location_id: LocationId | None,
) -> bool:
    """Whether the observer gets any observation row for the event."""
    if observer_id in event.participant_ids:
        return True
    if observer_location_id == event.location_id:
        return True
    disclosed_to = {
        recipient for disclosure in event.disclosures for recipient in disclosure.recipient_ids
    }
    return observer_id in disclosed_to


def permitted_facts(
    event: ObservableEvent,
    observer_id: CharacterId,
    observer_location_id: LocationId | None,
) -> list[PerceivedFact]:
    """Deterministic permitted fact set, ordered by fact key."""
    disclosed_keys = {
        disclosure.fact_key
        for disclosure in event.disclosures
        if observer_id in disclosure.recipient_ids
    }
    participant = observer_id in event.participant_ids
    present = observer_location_id == event.location_id

    permitted: list[PerceivedFact] = []
    for fact in event.facts:
        if fact.key in disclosed_keys:
            permitted.append(fact)
            continue
        if fact.concealed:
            continue
        if participant:
            permitted.append(fact)
        elif present and fact.visibility in (
            FactVisibility.PUBLIC,
            FactVisibility.SCENE,
        ):
            permitted.append(fact)
    return sorted(permitted, key=lambda f: f.key)


def phrase_observation(
    permitted: list[PerceivedFact], requested_keys: list[str]
) -> list[PerceivedFact]:
    """Select phrasing facts from the permitted set; reject anything else."""
    by_key = {fact.key: fact for fact in permitted}
    selected: list[PerceivedFact] = []
    for key in requested_keys:
        fact = by_key.get(key)
        if fact is None:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                f"phrasing requests a fact outside the permitted set: {key}",
            )
        selected.append(fact)
    return selected
