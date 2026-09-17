# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""CharacterDecisionGraph: bounded intent proposal (owned by S1-CHAR-001).

START -> validate invocation -> render perspective-safe prompt
-> call character model -> validate Intent schema
-> deterministic permission/knowledge precheck
-> repair once when structurally malformed
-> proposal or deterministic WAIT fallback -> END.

The graph never touches a repository and never authors another
character's reaction: nodes receive a gateway, a prompt template, and
the orchestrator-supplied perspective bundle. All canon writes happen
downstream in the commit transaction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from langgraph.graph import StateGraph
from pydantic import TypeAdapter, ValidationError

from worldsim.application.graphs.state import GraphInvocation, GraphState
from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    ModelGateway,
    ModelMalformedError,
    ModelProfile,
    ModelRateLimitedError,
    ModelRefusalError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from worldsim.domain.commands import (
    ActionIntent,
    AppealAction,
    CommunicateAction,
    MoveAction,
    SparAction,
    TransferAction,
    WaitAction,
)
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import derive_intent_id
from worldsim.domain.scenes import Intent

#: Versioned role prompt file (prompt lifecycle: repository file, versioned).
CHARACTER_PROMPT_VERSION = "character_decision.v2"

_ACTION_ADAPTER: TypeAdapter[ActionIntent] = TypeAdapter(ActionIntent)


class CharacterState(GraphState, total=False):
    """Graph state plus decision-local prompt/response fields."""

    rendered_context: str
    actor_alive: bool
    known_character_ids: list[str]
    location_ids: list[str]
    system_prompt: str
    user_prompt: str
    raw_response: str | None
    fallback_reason: str | None


@dataclass(frozen=True)
class CharacterGraphDeps:
    """Everything the graph may call: a gateway and static text."""

    gateway: ModelGateway
    profile: ModelProfile
    system_template: str
    max_tokens: int = 512
    repair_budget: int = 1


def prompt_path() -> Path:
    """Versioned prompt file next to the backend root."""
    return Path(__file__).resolve().parents[4] / "prompts" / f"{CHARACTER_PROMPT_VERSION}.md"


def load_character_prompt() -> str:
    """Read the versioned role prompt (fails loudly when missing)."""
    return prompt_path().read_text(encoding="utf-8")


def render_system_prompt(template: str) -> str:
    """Fill the response-schema placeholder (the only placeholder)."""
    schema_json = json.dumps(_ACTION_ADAPTER.json_schema(), indent=2, sort_keys=True)
    return template.replace("{{RESPONSE_SCHEMA}}", schema_json)


def render_user_prompt(rendered_context: str) -> str:
    """Perspective context plus output budget and fallback instruction."""
    return (
        f"{rendered_context}\n\n"
        "Output exactly one JSON object matching the response schema. "
        "Keep it short. When in doubt, wait."
    )


def precheck_action(
    action: ActionIntent,
    *,
    known_character_ids: frozenset[str],
    location_ids: frozenset[str],
) -> str | None:
    """Deterministic permission/knowledge precheck; reason or None when valid."""
    if isinstance(action, MoveAction):
        if str(action.destination_location_id) not in location_ids:
            return f"unknown destination: {action.destination_location_id}"
        return None
    if isinstance(action, CommunicateAction):
        if str(action.target_character_id) not in known_character_ids:
            return f"unknown target: {action.target_character_id}"
        return None
    if isinstance(action, SparAction):
        if str(action.target_character_id) not in known_character_ids:
            return f"unknown sparring partner: {action.target_character_id}"
        return None
    if isinstance(action, AppealAction):
        if (
            action.audience_location_id is not None
            and str(action.audience_location_id) not in location_ids
        ):
            return f"unknown audience ground: {action.audience_location_id}"
        return None
    if isinstance(action, TransferAction):
        if str(action.target_character_id) not in known_character_ids:
            return f"unknown recipient: {action.target_character_id}"
        return None
    return None


def _wrap_intent(invocation: GraphInvocation, action: ActionIntent) -> Intent:
    actor = invocation.actor_id
    assert actor is not None
    return Intent(
        id=derive_intent_id(invocation.world_id, invocation.snapshot_id, actor),
        world_id=invocation.world_id,
        snapshot_id=invocation.snapshot_id,
        phase_run_id=invocation.phase_run_id,
        author_character_id=actor,
        action=action,
        idempotency_key=f"character:{invocation.task_run_id}",
    )


def fallback_intent(invocation: GraphInvocation, reason: str) -> Intent:
    """Deterministic WAIT fallback; the player controls the attempt, never fate."""
    actor = invocation.actor_id
    assert actor is not None
    return _wrap_intent(
        invocation,
        WaitAction(character_id=actor, snapshot_id=invocation.snapshot_id),
    )


def _proposal(intent: Intent, *, fallback: bool, reason: str) -> dict[str, Any]:
    return {
        "intent": intent.model_dump(mode="json"),
        "fallback": fallback,
        "reason": reason,
    }


def build_character_graph(deps: CharacterGraphDeps) -> Any:
    """Compile the bounded decision graph around injected dependencies."""

    def validate_invocation(state: CharacterState) -> dict[str, Any]:
        rendered = state.get("rendered_context")
        if not isinstance(rendered, str) or not rendered:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, "decision needs rendered context")
        if state.get("actor_id") is None:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, "decision needs an actor")
        if state.get("actor_alive") is not True:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, "decision needs a living actor")
        return {"status": "invocation_valid"}

    def render_prompts(state: CharacterState) -> dict[str, Any]:
        rendered = state.get("rendered_context")
        assert isinstance(rendered, str) and rendered
        return {
            "system_prompt": render_system_prompt(deps.system_template),
            "user_prompt": render_user_prompt(rendered),
        }

    async def decide(state: CharacterState) -> dict[str, Any]:
        system = state.get("system_prompt")
        user = state.get("user_prompt")
        assert isinstance(system, str) and system
        assert isinstance(user, str) and user
        errors: list[str] = []
        repairs = 0
        try:
            result = await deps.gateway.complete(
                CompletionRequest(
                    prompt=user,
                    system=system,
                    max_tokens=deps.max_tokens,
                    json_mode=True,
                )
            )
        except (
            ModelTimeoutError,
            ModelRateLimitedError,
            ModelUnavailableError,
            ModelRefusalError,
            ModelMalformedError,
        ) as exc:
            reason = f"provider unavailable ({type(exc).__name__}); waiting"
            return _decide_result(
                state, fallback_intent(_invocation_of(state), reason), True, reason, [], 0, None
            )
        raw: str | None = result.text
        while True:
            try:
                action = _ACTION_ADAPTER.validate_json(raw)
            except ValidationError as exc:
                errors.append(f"attempt {repairs}: {exc.error_count()} schema errors")
                if repairs >= deps.repair_budget:
                    reason = f"unrepairable model output ({len(errors)} attempts); waiting"
                    return _decide_result(
                        state,
                        fallback_intent(_invocation_of(state), reason),
                        True,
                        reason,
                        errors,
                        repairs,
                        raw,
                    )
                repairs += 1
                try:
                    repaired = await deps.gateway.complete(
                        CompletionRequest(
                            prompt=(
                                f"{user}\n\nYour previous output was rejected "
                                f"({errors[-1]}). Output exactly one JSON object "
                                "matching the response schema."
                            ),
                            system=system,
                            max_tokens=deps.max_tokens,
                            json_mode=True,
                        )
                    )
                except (
                    ModelTimeoutError,
                    ModelRateLimitedError,
                    ModelUnavailableError,
                    ModelRefusalError,
                    ModelMalformedError,
                ) as exc:
                    reason = f"repair call failed ({type(exc).__name__}); waiting"
                    return _decide_result(
                        state,
                        fallback_intent(_invocation_of(state), reason),
                        True,
                        reason,
                        errors,
                        repairs,
                        raw,
                    )
                raw = repaired.text
                continue
            known = frozenset(str(v) for v in state.get("known_character_ids", []))
            locations = frozenset(str(v) for v in state.get("location_ids", []))
            denial = precheck_action(action, known_character_ids=known, location_ids=locations)
            if denial is not None:
                reason = f"precheck rejected the proposal ({denial}); waiting"
                return _decide_result(
                    state,
                    fallback_intent(_invocation_of(state), reason),
                    True,
                    reason,
                    errors,
                    repairs,
                    raw,
                )
            return _decide_result(
                state,
                _wrap_intent(_invocation_of(state), action),
                False,
                "valid",
                errors,
                repairs,
                raw,
            )

    builder = StateGraph(CharacterState)
    builder.add_node("validate_invocation", validate_invocation)
    builder.add_node("render_prompts", render_prompts)
    builder.add_node("decide", decide)
    builder.set_entry_point("validate_invocation")
    builder.add_edge("validate_invocation", "render_prompts")
    builder.add_edge("render_prompts", "decide")
    builder.set_finish_point("decide")
    return builder.compile()


def _invocation_of(state: CharacterState) -> GraphInvocation:
    """Rebuild the invocation correlation from seeded state."""
    task_raw = state.get("task_run_id")
    world_raw = state.get("world_id")
    phase_raw = state.get("phase_run_id")
    snapshot_raw = state.get("snapshot_id")
    assert (
        isinstance(task_raw, str)
        and isinstance(world_raw, str)
        and isinstance(phase_raw, str)
        and isinstance(snapshot_raw, str)
    )
    actor_raw = state.get("actor_id")
    scene_raw = state.get("scene_id")
    manifest_raw = state.get("context_manifest_id")
    return GraphInvocation(
        graph_name="character-decision",
        graph_version="v1",
        task_run_id=UUID(task_raw),
        world_id=UUID(world_raw),
        phase_run_id=UUID(phase_raw),
        snapshot_id=UUID(snapshot_raw),
        scene_id=UUID(str(scene_raw)) if scene_raw else None,
        actor_id=UUID(str(actor_raw)) if actor_raw else None,
        context_manifest_id=UUID(str(manifest_raw)) if manifest_raw else None,
        role=str(state.get("role", "character_decision")),
        profile_version=str(state.get("profile_version", "unspecified")),
        prompt_version=str(state.get("prompt_version", CHARACTER_PROMPT_VERSION)),
    )


def _decide_result(
    state: CharacterState,
    intent: Intent,
    fallback: bool,
    reason: str,
    errors: list[str],
    repairs: int,
    raw: str | None,
) -> dict[str, Any]:
    return {
        "proposal": _proposal(intent, fallback=fallback, reason=reason),
        "validation_errors": errors,
        "repair_count": repairs,
        "raw_response": raw,
        "fallback_reason": reason if fallback else None,
        "status": "fallback" if fallback else "proposed",
    }
