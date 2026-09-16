"""CharacterDecisionGraph checks (owned by S1-CHAR-001)."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from worldsim.application.graphs.character import (
    CHARACTER_PROMPT_VERSION,
    CharacterGraphDeps,
    build_character_graph,
    fallback_intent,
    load_character_prompt,
    precheck_action,
)
from worldsim.application.graphs.runtime import invoke
from worldsim.application.graphs.state import GraphInvocation
from worldsim.application.ports.model_gateway import (
    ModelRateLimitedError,
    ModelTimeoutError,
)
from worldsim.domain.commands import CommunicateAction, MoveAction, WaitAction
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import CHARACTER_FAKE_PROFILE

SECRET = "A davors the northern pass at dawn"


def _deps(gateway: FakeGateway) -> CharacterGraphDeps:
    return CharacterGraphDeps(
        gateway=gateway,
        profile=CHARACTER_FAKE_PROFILE,
        system_template=load_character_prompt(),
    )


def _invocation(
    actor: uuid.UUID, rendered: str, snapshot: uuid.UUID | None = None, **overrides: Any
) -> GraphInvocation:
    base: dict[str, Any] = {
        "graph_name": "character-decision",
        "graph_version": "v1",
        "task_run_id": uuid.uuid4(),
        "world_id": uuid.uuid4(),
        "phase_run_id": uuid.uuid4(),
        "snapshot_id": snapshot or uuid.uuid4(),
        "actor_id": actor,
        "role": "character_decision",
        "profile_version": CHARACTER_FAKE_PROFILE.version,
        "prompt_version": CHARACTER_PROMPT_VERSION,
        "input": {
            "rendered_context": rendered,
            "actor_alive": True,
            "known_character_ids": [],
            "location_ids": [],
        },
    }
    if overrides:
        base["input"] = {**base["input"], **overrides}
    return GraphInvocation(**base)


def _wait_json(actor: uuid.UUID, snapshot: uuid.UUID) -> str:
    return json.dumps({"family": "wait", "character_id": str(actor), "snapshot_id": str(snapshot)})


def test_valid_intent_proposed() -> None:
    actor, snapshot = uuid.uuid4(), uuid.uuid4()
    gateway = FakeGateway(profile=CHARACTER_FAKE_PROFILE)
    gateway.enqueue_text(_wait_json(actor, snapshot))
    invocation = _invocation(actor, "You are Wren. Hearth. Dawn.", snapshot=snapshot)

    result = asyncio.run(invoke(build_character_graph(_deps(gateway)), invocation))

    assert result["status"] == "proposed"
    assert result["repair_count"] == 0
    assert result["proposal"]["fallback"] is False
    intent = result["proposal"]["intent"]
    assert intent["action"]["family"] == "wait"
    assert intent["author_character_id"] == str(actor)
    assert intent["snapshot_id"] == str(snapshot)
    assert intent["idempotency_key"] == f"character:{invocation.task_run_id}"


def test_malformed_output_repaired_once() -> None:
    actor, snapshot = uuid.uuid4(), uuid.uuid4()
    gateway = FakeGateway(profile=CHARACTER_FAKE_PROFILE)
    gateway.enqueue_text("{not json")
    gateway.enqueue_text(_wait_json(actor, snapshot))

    result = asyncio.run(
        invoke(build_character_graph(_deps(gateway)), _invocation(actor, "You are Wren."))
    )

    assert result["status"] == "proposed"
    assert result["repair_count"] == 1
    assert result["proposal"]["fallback"] is False
    assert len(gateway.sent_requests) == 2
    assert "rejected" in gateway.sent_requests[1].prompt


def test_repeated_malformed_falls_back_to_wait() -> None:
    actor = uuid.uuid4()
    gateway = FakeGateway(profile=CHARACTER_FAKE_PROFILE)
    gateway.enqueue_text("{bad one")
    gateway.enqueue_text("{bad two")

    result = asyncio.run(
        invoke(build_character_graph(_deps(gateway)), _invocation(actor, "You are Wren."))
    )

    assert result["status"] == "fallback"
    assert result["proposal"]["fallback"] is True
    assert result["proposal"]["intent"]["action"]["family"] == "wait"
    assert "unrepairable" in result["proposal"]["reason"]
    assert gateway.pending_count() == 0


def test_timeout_uses_safe_fallback_without_retry() -> None:
    actor = uuid.uuid4()
    gateway = FakeGateway(profile=CHARACTER_FAKE_PROFILE)
    gateway.enqueue_error(ModelTimeoutError("timed out"))

    result = asyncio.run(
        invoke(build_character_graph(_deps(gateway)), _invocation(actor, "You are Wren."))
    )

    assert result["status"] == "fallback"
    assert result["proposal"]["intent"]["action"]["family"] == "wait"
    assert "ModelTimeoutError" in result["proposal"]["reason"]
    assert gateway.pending_count() == 0


def test_rate_limit_uses_safe_fallback() -> None:
    actor = uuid.uuid4()
    gateway = FakeGateway(profile=CHARACTER_FAKE_PROFILE)
    gateway.enqueue_error(ModelRateLimitedError("slow down", retry_after_s=5.0))

    result = asyncio.run(
        invoke(build_character_graph(_deps(gateway)), _invocation(actor, "You are Wren."))
    )

    assert result["status"] == "fallback"
    assert "ModelRateLimitedError" in result["proposal"]["reason"]


def test_unknown_target_rejected_to_fallback() -> None:
    actor, snapshot = uuid.uuid4(), uuid.uuid4()
    gateway = FakeGateway(profile=CHARACTER_FAKE_PROFILE)
    gateway.enqueue_text(
        json.dumps(
            {
                "family": "communicate",
                "character_id": str(actor),
                "snapshot_id": str(snapshot),
                "target_character_id": str(uuid.uuid4()),
                "topic": "the road",
            }
        )
    )

    result = asyncio.run(
        invoke(
            build_character_graph(_deps(gateway)),
            _invocation(actor, "You are Wren.", known_character_ids=[str(uuid.uuid4())]),
        )
    )

    assert result["status"] == "fallback"
    assert "unknown target" in result["proposal"]["reason"]
    # No repair call for a knowledge gap: one model call total.
    assert len(gateway.sent_requests) == 1


def test_unknown_destination_rejected_to_fallback() -> None:
    actor, snapshot = uuid.uuid4(), uuid.uuid4()
    gateway = FakeGateway(profile=CHARACTER_FAKE_PROFILE)
    gateway.enqueue_text(
        json.dumps(
            {
                "family": "move",
                "character_id": str(actor),
                "snapshot_id": str(snapshot),
                "destination_location_id": str(uuid.uuid4()),
            }
        )
    )

    result = asyncio.run(
        invoke(
            build_character_graph(_deps(gateway)),
            _invocation(actor, "You are Wren.", location_ids=[str(uuid.uuid4())]),
        )
    )

    assert result["status"] == "fallback"
    assert "unknown destination" in result["proposal"]["reason"]


def test_voice_and_versions_reach_provider() -> None:
    actor = uuid.uuid4()
    gateway = FakeGateway(profile=CHARACTER_FAKE_PROFILE)
    gateway.enqueue_text(_wait_json(actor, uuid.uuid4()))
    voice = "Wren speaks in short clipped scouting cant"
    invocation = _invocation(actor, f"You are Wren. Voice: {voice}.")

    result = asyncio.run(invoke(build_character_graph(_deps(gateway)), invocation))

    assert result["status"] == "proposed"
    assert result["profile_version"] == CHARACTER_FAKE_PROFILE.version
    assert result["prompt_version"] == CHARACTER_PROMPT_VERSION
    request = gateway.sent_requests[0]
    assert voice in request.prompt
    assert request.system is not None and "never invent places" in request.system
    assert request.json_mode is True


def test_private_secret_never_sent() -> None:
    actor = uuid.uuid4()
    gateway = FakeGateway(profile=CHARACTER_FAKE_PROFILE)
    gateway.enqueue_text(_wait_json(actor, uuid.uuid4()))
    # B's assembled context: the secret was excluded upstream.
    rendered = "You are Ash. The market opens at dawn."

    result = asyncio.run(
        invoke(build_character_graph(_deps(gateway)), _invocation(actor, rendered))
    )

    assert result["status"] == "proposed"
    for request in gateway.sent_requests:
        assert SECRET not in request.prompt
        assert SECRET not in (request.system or "")


def test_precheck_unit_cases() -> None:
    actor, snapshot = uuid.uuid4(), uuid.uuid4()
    known = frozenset({str(uuid.uuid4())})
    assert (
        precheck_action(
            CommunicateAction(
                character_id=actor,
                snapshot_id=snapshot,
                target_character_id=uuid.uuid4(),
                topic="hi",
            ),
            known_character_ids=known,
            location_ids=frozenset(),
        )
        is not None
    )
    assert (
        precheck_action(
            MoveAction(
                character_id=actor,
                snapshot_id=snapshot,
                destination_location_id=uuid.uuid4(),
            ),
            known_character_ids=known,
            location_ids=frozenset(),
        )
        is not None
    )
    assert (
        precheck_action(
            WaitAction(character_id=actor, snapshot_id=snapshot),
            known_character_ids=known,
            location_ids=frozenset(),
        )
        is None
    )


def test_fallback_helper_builds_wait() -> None:
    actor = uuid.uuid4()
    invocation = _invocation(actor, "ctx")
    intent = fallback_intent(invocation, "reason")
    assert intent.action.family == "wait"  # type: ignore[comparison-overlap]
    assert intent.author_character_id == actor
