"""S1-CONTRACT-001: strict scene contract examples (owned by S1-CONTRACT-001)."""

from __future__ import annotations

import uuid
from uuid import UUID

import pytest
from helpers_sim import make_world_view
from pydantic import ValidationError

from worldsim.domain.commands import CommunicateAction, MoveAction
from worldsim.domain.effects import AdvanceClockEffect
from worldsim.domain.enums import (
    ActionFamily,
    IntentStatus,
    NarrationKind,
    ParticipantRole,
    ResolutionOutcome,
    ResolverKind,
    SceneStatus,
)
from worldsim.domain.narration import NarrationBeat
from worldsim.domain.scenes import (
    Attempt,
    DesiredEffect,
    Intent,
    Reaction,
    Resolution,
    Scene,
    SceneParticipant,
    ValidationIssue,
    scene_transition_allowed,
)


def _communicate(author: UUID, target: UUID, snapshot: UUID) -> CommunicateAction:
    return CommunicateAction(
        character_id=author,
        snapshot_id=snapshot,
        target_character_id=target,
        topic="the market road",
    )


def _intent(author: UUID, target: UUID, snapshot: UUID, key: str = "intent-1") -> Intent:
    return Intent(
        id=uuid.uuid4(),
        world_id=uuid.uuid4(),
        snapshot_id=snapshot,
        author_character_id=author,
        action=_communicate(author, target, snapshot),
        desired_effects=[DesiredEffect(effect_family="communicate", description="talk")],
        idempotency_key=key,
    )


def test_intent_round_trip() -> None:
    author, target, snapshot = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    intent = _intent(author, target, snapshot)
    assert intent.status == IntentStatus.PROPOSED
    assert intent.action.family == ActionFamily.COMMUNICATE
    again = Intent.model_validate(intent.model_dump(mode="json"))
    assert again == intent


def test_intent_rejects_extra_fields() -> None:
    author, target, snapshot = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    payload = _intent(author, target, snapshot).model_dump(mode="json")
    payload["mood"] = "sneaky"
    with pytest.raises(ValidationError):
        Intent.model_validate(payload)


def test_intent_rejects_self_dialogue() -> None:
    from worldsim.domain.errors import DomainError
    from worldsim.domain.rules.actions import check_communicate

    view = make_world_view()
    wren = view.characters[0]
    snapshot = uuid.uuid4()
    with pytest.raises(DomainError, match="another character"):
        check_communicate(
            wren,
            CommunicateAction(
                character_id=wren.id,
                snapshot_id=snapshot,
                target_character_id=wren.id,
                topic="plans",
            ),
        )
    with pytest.raises(DomainError, match="topic"):
        check_communicate(
            wren,
            CommunicateAction(
                character_id=wren.id,
                snapshot_id=snapshot,
                target_character_id=view.characters[1].id,
                topic="  ",
            ),
        )
    check_communicate(
        wren,
        CommunicateAction(
            character_id=wren.id,
            snapshot_id=snapshot,
            target_character_id=view.characters[1].id,
            topic="the market road",
        ),
    )


def test_stage0_path_rejects_dialogue_family() -> None:
    from worldsim.domain.errors import DomainError, ErrorCode
    from worldsim.domain.rules.actions import check_intent

    view = make_world_view()
    wren = view.characters[0]
    action = CommunicateAction(
        character_id=wren.id,
        snapshot_id=uuid.uuid4(),
        target_character_id=view.characters[1].id,
        topic="the market road",
    )
    with pytest.raises(DomainError) as excinfo:
        check_intent(action, view)
    assert excinfo.value.code is ErrorCode.UNSUPPORTED_ACTION


def test_resolution_rejects_unknown_effect() -> None:
    from pydantic import TypeAdapter

    from worldsim.domain.effects import DomainEffect

    scene, world = uuid.uuid4(), uuid.uuid4()
    adapter = TypeAdapter(list[DomainEffect])
    with pytest.raises(ValidationError):
        adapter.validate_python(
            [
                {
                    "schema_version": 1,
                    "affected_ids": [str(world)],
                    "expected_versions": {str(world): 1},
                    "effect_type": "summon_dragon",
                }
            ]
        )
    with pytest.raises(ValidationError):
        Resolution(
            id=uuid.uuid4(),
            world_id=world,
            scene_id=scene,
            outcome=ResolutionOutcome.SUCCESS,
            resolver=ResolverKind.DETERMINISTIC,
            effects=adapter.validate_python(
                [
                    {
                        "schema_version": 1,
                        "affected_ids": [str(world)],
                        "expected_versions": {str(world): 1},
                        "effect_type": "advance_clock",
                        "from_index": 2,
                        "to_index": 1,
                    }
                ]
            ),
        )


def test_resolution_accepts_typed_effects_round_trip() -> None:
    scene, world = uuid.uuid4(), uuid.uuid4()
    resolution = Resolution(
        id=uuid.uuid4(),
        world_id=world,
        scene_id=scene,
        outcome=ResolutionOutcome.PARTIAL,
        resolver=ResolverKind.DETERMINISTIC,
        effects=[
            AdvanceClockEffect(
                affected_ids=[world],
                expected_versions={str(world): 1},
                from_index=1,
                to_index=2,
            )
        ],
        rationale="clock moved while they talked",
    )
    assert Resolution.model_validate(resolution.model_dump(mode="json")) == resolution


def test_scene_transition_map() -> None:
    assert scene_transition_allowed(SceneStatus.PROPOSED, SceneStatus.VALIDATING)
    assert scene_transition_allowed(SceneStatus.RESOLVED, SceneStatus.COMMITTED)
    assert scene_transition_allowed(SceneStatus.RETRYABLE_FAILED, SceneStatus.RESOLVING)
    assert not scene_transition_allowed(SceneStatus.PROPOSED, SceneStatus.COMMITTED)
    assert not scene_transition_allowed(SceneStatus.COMMITTED, SceneStatus.RESOLVING)
    assert not scene_transition_allowed(SceneStatus.INVALID, SceneStatus.VALIDATING)
    assert not scene_transition_allowed(SceneStatus.TERMINAL_FAILED, SceneStatus.READY)


def test_scene_requires_participants_and_intents() -> None:
    ids = {
        "id": uuid.uuid4(),
        "world_id": uuid.uuid4(),
        "phase_run_id": uuid.uuid4(),
        "snapshot_id": uuid.uuid4(),
    }
    with pytest.raises(ValidationError):
        Scene(
            id=ids["id"],
            world_id=ids["world_id"],
            phase_run_id=ids["phase_run_id"],
            snapshot_id=ids["snapshot_id"],
            participants=[],
            intent_ids=[uuid.uuid4()],
        )
    scene = Scene(
        id=ids["id"],
        world_id=ids["world_id"],
        phase_run_id=ids["phase_run_id"],
        snapshot_id=ids["snapshot_id"],
        participants=[SceneParticipant(character_id=uuid.uuid4(), role=ParticipantRole.INITIATOR)],
        intent_ids=[uuid.uuid4()],
    )
    assert scene.status == SceneStatus.PROPOSED
    assert scene.beat_budget == 8


def test_attempt_reaction_linkage() -> None:
    author, target, snapshot = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    intent = _intent(author, target, snapshot)
    attempt = Attempt(
        id=uuid.uuid4(),
        world_id=intent.world_id,
        intent_id=intent.id,
        actor_character_id=author,
        observable_summary="Wren hails Ash across the market.",
    )
    reaction = Reaction(
        id=uuid.uuid4(),
        world_id=intent.world_id,
        attempt_id=attempt.id,
        reactor_character_id=target,
        action=MoveAction(
            character_id=target,
            snapshot_id=snapshot,
            destination_location_id=uuid.uuid4(),
        ),
    )
    assert reaction.attempt_id == attempt.id
    assert attempt.intent_id == intent.id


def test_narration_beats() -> None:
    event, world = uuid.uuid4(), uuid.uuid4()
    narrator = NarrationBeat(
        id=uuid.uuid4(), world_id=world, source_event_id=event, text="Dawn breaks."
    )
    assert narrator.speaker_id is None
    assert narrator.kind == NarrationKind.NARRATION
    dialogue = NarrationBeat(
        id=uuid.uuid4(),
        world_id=world,
        source_event_id=event,
        speaker_id=uuid.uuid4(),
        kind=NarrationKind.DIALOGUE,
        text="Take the market road.",
        emotion_hint="warm",
    )
    assert NarrationBeat.model_validate(dialogue.model_dump(mode="json")) == dialogue
    with pytest.raises(ValidationError):
        NarrationBeat(id=uuid.uuid4(), world_id=world, source_event_id=event, text="")


def test_validation_issue_shape() -> None:
    issue = ValidationIssue(location="action.topic", code="blank", message="topic is blank")
    assert issue.location == "action.topic"
