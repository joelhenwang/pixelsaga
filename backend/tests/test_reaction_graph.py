"""Bounded ReactionGraph checks (owned by S1-REACT-001)."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from worldsim.application.graphs.reaction import (
    REACTION_PROMPT_VERSION,
    ReactionGraphDeps,
    build_reaction_graph,
    check_eligibility,
    load_reaction_prompt,
)
from worldsim.application.graphs.runtime import invoke
from worldsim.application.graphs.state import GraphInvocation
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import REACTION_FAKE_PROFILE

HIDDEN_RATIONALE = "Wren plots betrayal at midnight"


def _deps(gateway: FakeGateway) -> ReactionGraphDeps:
    return ReactionGraphDeps(
        gateway=gateway,
        profile=REACTION_FAKE_PROFILE,
        system_template=load_reaction_prompt(),
    )


def _invocation(
    reactor: uuid.UUID,
    attempt_actor: uuid.UUID,
    attempt_id: uuid.UUID,
    **overrides: Any,
) -> GraphInvocation:
    payload: dict[str, Any] = {
        "reactor_context": "You are Ash. The market at dawn.",
        "observable_summary": "Wren nods at you.",
        "reactor_alive": True,
        "reactor_location_id": "market",
        "event_location_id": "market",
        "participant_ids": [str(reactor)],
        "known_character_ids": [],
        "location_ids": ["market"],
        "beats_remaining": 8,
        "attempt_id": str(attempt_id),
        "attempt_actor_id": str(attempt_actor),
    }
    payload.update(overrides)
    return GraphInvocation(
        graph_name="reaction",
        graph_version="v1",
        task_run_id=uuid.uuid4(),
        world_id=uuid.uuid4(),
        phase_run_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        scene_id=uuid.uuid4(),
        actor_id=reactor,
        role="reaction",
        profile_version=REACTION_FAKE_PROFILE.version,
        prompt_version=REACTION_PROMPT_VERSION,
        input=payload,
    )


def _observe_json(reactor: uuid.UUID, snapshot: uuid.UUID) -> str:
    return json.dumps(
        {
            "family": "observe",
            "character_id": str(reactor),
            "snapshot_id": str(snapshot),
            "focus": "Wren",
        }
    )


def test_eligible_target_reacts_from_own_perspective() -> None:
    reactor, initiator, attempt = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    snapshot = uuid.uuid4()
    gateway = FakeGateway(profile=REACTION_FAKE_PROFILE)
    gateway.enqueue_text(_observe_json(reactor, snapshot))

    result = asyncio.run(
        invoke(
            build_reaction_graph(_deps(gateway)),
            _invocation(reactor, initiator, attempt),
        )
    )

    assert result["status"] == "reacted"
    assert result["proposal"]["reacted"] is True
    reaction = result["proposal"]["reaction"]
    assert reaction["reactor_character_id"] == str(reactor)
    assert reaction["attempt_id"] == str(attempt)
    assert reaction["action"]["family"] == "observe"
    request = gateway.sent_requests[0]
    assert "You are Ash" in request.prompt
    assert "Wren nods at you." in request.prompt


def test_absent_target_receives_no_call() -> None:
    reactor, initiator, attempt = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    gateway = FakeGateway(profile=REACTION_FAKE_PROFILE)

    result = asyncio.run(
        invoke(
            build_reaction_graph(_deps(gateway)),
            _invocation(
                reactor,
                initiator,
                attempt,
                participant_ids=[],
                reactor_location_id="hearth",
                event_location_id="market",
            ),
        )
    )

    assert result["status"] == "no_reaction"
    assert result["proposal"]["reacted"] is False
    assert "absent or unaware" in result["proposal"]["reason"]
    assert gateway.sent_requests == []


def test_initiator_cannot_author_reaction() -> None:
    actor, attempt = uuid.uuid4(), uuid.uuid4()
    gateway = FakeGateway(profile=REACTION_FAKE_PROFILE)

    result = asyncio.run(
        invoke(
            build_reaction_graph(_deps(gateway)),
            _invocation(actor, actor, attempt),
        )
    )

    assert result["status"] == "no_reaction"
    assert "initiator cannot react" in result["proposal"]["reason"]
    assert gateway.sent_requests == []


def test_exhausted_beats_stop_before_call() -> None:
    reactor, initiator, attempt = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    gateway = FakeGateway(profile=REACTION_FAKE_PROFILE)

    result = asyncio.run(
        invoke(
            build_reaction_graph(_deps(gateway)),
            _invocation(reactor, initiator, attempt, beats_remaining=0),
        )
    )

    assert result["status"] == "no_reaction"
    assert "beat budget exhausted" in result["proposal"]["reason"]
    assert gateway.sent_requests == []


def test_malformed_repaired_within_budget() -> None:
    reactor, initiator, attempt = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    snapshot = uuid.uuid4()
    gateway = FakeGateway(profile=REACTION_FAKE_PROFILE)
    gateway.enqueue_text("{broken")
    gateway.enqueue_text(_observe_json(reactor, snapshot))

    result = asyncio.run(
        invoke(
            build_reaction_graph(_deps(gateway)),
            _invocation(reactor, initiator, attempt),
        )
    )

    assert result["status"] == "reacted"
    assert result["repair_count"] == 1
    assert len(gateway.sent_requests) == 2


def test_single_beat_forbids_repair_call() -> None:
    reactor, initiator, attempt = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    gateway = FakeGateway(profile=REACTION_FAKE_PROFILE)
    gateway.enqueue_text("{broken")
    gateway.enqueue_text(_observe_json(reactor, uuid.uuid4()))

    result = asyncio.run(
        invoke(
            build_reaction_graph(_deps(gateway)),
            _invocation(reactor, initiator, attempt, beats_remaining=1),
        )
    )

    assert result["status"] == "no_reaction"
    assert len(gateway.sent_requests) == 1
    assert gateway.pending_count() == 1


def test_hidden_rationale_never_reaches_prompt() -> None:
    reactor, initiator, attempt = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    gateway = FakeGateway(profile=REACTION_FAKE_PROFILE)
    gateway.enqueue_text(_observe_json(reactor, uuid.uuid4()))

    result = asyncio.run(
        invoke(
            build_reaction_graph(_deps(gateway)),
            _invocation(reactor, initiator, attempt),
        )
    )

    assert result["status"] == "reacted"
    for request in gateway.sent_requests:
        assert HIDDEN_RATIONALE not in request.prompt
        assert HIDDEN_RATIONALE not in (request.system or "")


def test_call_count_stays_inside_beats() -> None:
    reactor, initiator, attempt = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    gateway = FakeGateway(profile=REACTION_FAKE_PROFILE)
    gateway.enqueue_text(_observe_json(reactor, uuid.uuid4()))

    result = asyncio.run(
        invoke(
            build_reaction_graph(_deps(gateway)),
            _invocation(reactor, initiator, attempt, beats_remaining=3),
        )
    )

    assert result["status"] == "reacted"
    assert len(gateway.sent_requests) <= 3


def test_eligibility_unit_cases() -> None:
    reactor, initiator = "a", "b"
    assert (
        check_eligibility(
            reactor_id=reactor,
            attempt_actor_id=initiator,
            reactor_alive=True,
            beats_remaining=2,
            participant_ids=[reactor],
            reactor_location_id=None,
            event_location_id=None,
        )[0]
        is True
    )
    assert (
        check_eligibility(
            reactor_id=reactor,
            attempt_actor_id=reactor,
            reactor_alive=True,
            beats_remaining=2,
            participant_ids=[reactor],
            reactor_location_id=None,
            event_location_id=None,
        )[0]
        is False
    )
