"""Observation fact-set service checks (owned by S1-PERCEPT-001)."""

from __future__ import annotations

import uuid

import pytest

from worldsim.domain.errors import DomainError
from worldsim.domain.perception import (
    Disclosure,
    FactChannel,
    FactVisibility,
    ObservableEvent,
    PerceivedFact,
)
from worldsim.domain.rules.perception import (
    is_eligible,
    permitted_facts,
    phrase_observation,
)


def _event() -> ObservableEvent:
    a, _b = uuid.uuid4(), uuid.uuid4()
    return ObservableEvent(
        event_id=uuid.uuid4(),
        world_id=uuid.uuid4(),
        location_id=uuid.uuid4(),
        participant_ids=[a],
        facts=[
            PerceivedFact(key="greeting", value="Wren nods", visibility=FactVisibility.SCENE),
            PerceivedFact(
                key="whisper",
                value="the pass",
                visibility=FactVisibility.PRIVATE,
                channel=FactChannel.DIRECT,
            ),
            PerceivedFact(
                key="sleight",
                value="a lifted coin",
                visibility=FactVisibility.SCENE,
                concealed=True,
            ),
        ],
        disclosures=[],
    )


def test_participant_sees_everything_unconcealed() -> None:
    event = _event()
    participant = event.participant_ids[0]
    assert [f.key for f in permitted_facts(event, participant, event.location_id)] == [
        "greeting",
        "whisper",
    ]
    assert is_eligible(event, participant, None)


def test_nearby_observer_misses_private_and_concealed() -> None:
    event = _event()
    observer = uuid.uuid4()
    assert [f.key for f in permitted_facts(event, observer, event.location_id)] == ["greeting"]
    assert is_eligible(event, observer, event.location_id)


def test_absent_character_gets_nothing() -> None:
    event = _event()
    absent = uuid.uuid4()
    assert permitted_facts(event, absent, uuid.uuid4()) == []
    assert not is_eligible(event, absent, uuid.uuid4())


def test_concealed_action_hidden_from_everyone_present() -> None:
    event = _event()
    keys = {f.key for f in permitted_facts(event, uuid.uuid4(), event.location_id)}
    assert "sleight" not in keys
    participant_keys = {
        f.key for f in permitted_facts(event, event.participant_ids[0], event.location_id)
    }
    assert "sleight" not in participant_keys


def test_explicit_disclosure_reaches_absent_recipient() -> None:
    event = _event()
    recipient = uuid.uuid4()
    disclosed = event.model_copy(
        update={
            "disclosures": [Disclosure(fact_key="sleight", recipient_ids=[recipient])],
        }
    )
    assert [f.key for f in permitted_facts(disclosed, recipient, uuid.uuid4())] == ["sleight"]
    assert is_eligible(disclosed, recipient, uuid.uuid4())
    # Disclosure does not widen anyone else's set.
    assert permitted_facts(disclosed, uuid.uuid4(), disclosed.location_id) == [
        f for f in permitted_facts(event, uuid.uuid4(), event.location_id)
    ]


def test_phrasing_cannot_add_forbidden_fact() -> None:
    event = _event()
    observer = uuid.uuid4()
    permitted = permitted_facts(event, observer, event.location_id)
    assert [f.key for f in phrase_observation(permitted, ["greeting"])] == ["greeting"]
    with pytest.raises(DomainError):
        phrase_observation(permitted, ["greeting", "whisper"])
    with pytest.raises(DomainError):
        phrase_observation(permitted, ["sleight"])
