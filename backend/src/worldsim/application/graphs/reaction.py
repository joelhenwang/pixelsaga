# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""ReactionGraph: bounded reaction proposal (owned by S1-REACT-001).

START -> reaction eligibility -> observable-attempt context
-> call reaction model -> validate schema -> one repair
-> reaction or deterministic no-reaction -> END.

Eligibility is deterministic and runs before any model call: the
initiator cannot react to their own attempt, absent or unaware targets
receive no call, and an exhausted beat budget stops the graph cold.
The reactor sees only their own perspective plus the observable
attempt summary; the initiator's hidden rationale never enters.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from langgraph.graph import StateGraph
from pydantic import TypeAdapter, ValidationError

from worldsim.application.graphs.character import precheck_action
from worldsim.application.graphs.state import GraphState
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
from worldsim.domain.commands import ActionIntent
from worldsim.domain.ids import derive_reaction_id
from worldsim.domain.scenes import Reaction

#: Versioned reaction prompt file.
REACTION_PROMPT_VERSION = "reaction.v1"

_ACTION_ADAPTER: TypeAdapter[ActionIntent] = TypeAdapter(ActionIntent)


class ReactionState(GraphState, total=False):
    """Graph state plus reaction-local eligibility and prompt fields."""

    reactor_context: str
    observable_summary: str
    reactor_alive: bool
    reactor_location_id: str | None
    event_location_id: str | None
    participant_ids: list[str]
    known_character_ids: list[str]
    location_ids: list[str]
    beats_remaining: int
    attempt_id: str
    attempt_actor_id: str
    eligible: bool
    eligibility_reason: str
    system_prompt: str
    user_prompt: str
    raw_response: str | None


@dataclass(frozen=True)
class ReactionGraphDeps:
    """Everything the graph may call: a gateway and static text."""

    gateway: ModelGateway
    profile: ModelProfile
    system_template: str
    max_tokens: int = 256
    repair_budget: int = 1


def prompt_path() -> Path:
    """Versioned prompt file next to the backend root."""
    return Path(__file__).resolve().parents[4] / "prompts" / f"{REACTION_PROMPT_VERSION}.md"


def load_reaction_prompt() -> str:
    """Read the versioned reaction prompt (fails loudly when missing)."""
    return prompt_path().read_text(encoding="utf-8")


def render_system_prompt(template: str) -> str:
    """Fill the response-schema placeholder (the only placeholder)."""
    schema_json = json.dumps(_ACTION_ADAPTER.json_schema(), indent=2, sort_keys=True)
    return template.replace("{{RESPONSE_SCHEMA}}", schema_json)


def render_user_prompt(reactor_context: str, observable_summary: str) -> str:
    """Reactor perspective plus the observable attempt (never hidden rationale)."""
    return (
        f"{reactor_context}\n\n"
        f"Observable attempt: {observable_summary}\n\n"
        "React from your own perspective to exactly what you perceived. "
        "Output exactly one JSON object matching the response schema."
    )


def check_eligibility(
    *,
    reactor_id: str,
    attempt_actor_id: str,
    reactor_alive: bool,
    beats_remaining: int,
    participant_ids: list[str],
    reactor_location_id: str | None,
    event_location_id: str | None,
) -> tuple[bool, str]:
    """Deterministic reaction eligibility with a stable reason."""
    if reactor_id == attempt_actor_id:
        return False, "initiator cannot react to its own attempt"
    if not reactor_alive:
        return False, "reactor is not alive"
    if beats_remaining < 1:
        return False, "beat budget exhausted"
    if reactor_id in participant_ids:
        return True, "reactor participates in the scene"
    if reactor_location_id is not None and reactor_location_id == event_location_id:
        return True, "reactor perceives the event location"
    return False, "reactor absent or unaware"


def _no_reaction(reason: str, errors: list[str], repairs: int) -> dict[str, Any]:
    return {
        "proposal": {"reaction": None, "reacted": False, "reason": reason},
        "validation_errors": errors,
        "repair_count": repairs,
        "raw_response": None,
        "status": "no_reaction",
    }


def build_reaction_graph(deps: ReactionGraphDeps) -> Any:
    """Compile the bounded reaction graph around injected dependencies."""

    def validate_eligibility(state: ReactionState) -> dict[str, Any]:
        actor_raw = state.get("actor_id")
        assert isinstance(actor_raw, str) and actor_raw
        attempt_actor_raw = state.get("attempt_actor_id")
        assert isinstance(attempt_actor_raw, str) and attempt_actor_raw
        alive = state.get("reactor_alive") is True
        beats_raw = state.get("beats_remaining")
        assert isinstance(beats_raw, int)
        participants_raw = state.get("participant_ids")
        assert isinstance(participants_raw, list)
        eligible, reason = check_eligibility(
            reactor_id=actor_raw,
            attempt_actor_id=attempt_actor_raw,
            reactor_alive=alive,
            beats_remaining=beats_raw,
            participant_ids=[str(v) for v in participants_raw],
            reactor_location_id=str(state.get("reactor_location_id") or "") or None,
            event_location_id=str(state.get("event_location_id") or "") or None,
        )
        return {"eligible": eligible, "eligibility_reason": reason, "status": "eligibility_checked"}

    def render_prompts(state: ReactionState) -> dict[str, Any]:
        context = state.get("reactor_context")
        summary = state.get("observable_summary")
        assert isinstance(context, str) and context
        assert isinstance(summary, str) and summary
        return {
            "system_prompt": render_system_prompt(deps.system_template),
            "user_prompt": render_user_prompt(context, summary),
        }

    async def decide(state: ReactionState) -> dict[str, Any]:
        system = state.get("system_prompt")
        user = state.get("user_prompt")
        assert isinstance(system, str) and isinstance(user, str)
        beats_raw = state.get("beats_remaining")
        repairs_allowed = deps.repair_budget if isinstance(beats_raw, int) and beats_raw >= 2 else 0
        errors: list[str] = []
        repairs = 0
        try:
            result = await deps.gateway.complete(
                CompletionRequest(
                    prompt=user, system=system, max_tokens=deps.max_tokens, json_mode=True
                )
            )
        except (
            ModelTimeoutError,
            ModelRateLimitedError,
            ModelUnavailableError,
            ModelRefusalError,
            ModelMalformedError,
        ) as exc:
            return _no_reaction(f"provider failed ({type(exc).__name__})", [], 0)
        raw: str | None = result.text
        while True:
            try:
                action = _ACTION_ADAPTER.validate_json(raw)
            except ValidationError as exc:
                errors.append(f"attempt {repairs}: {exc.error_count()} schema errors")
                if repairs >= repairs_allowed:
                    return _no_reaction(
                        f"unrepairable reaction output ({len(errors)} attempts)", errors, repairs
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
                    return _no_reaction(
                        f"repair call failed ({type(exc).__name__})", errors, repairs
                    )
                raw = repaired.text
                continue
            known = frozenset(str(v) for v in state.get("known_character_ids", []))
            locations = frozenset(str(v) for v in state.get("location_ids", []))
            denial = precheck_action(action, known_character_ids=known, location_ids=locations)
            if denial is not None:
                return _no_reaction(f"precheck rejected the reaction ({denial})", errors, repairs)
            return _reaction_result(state, action, errors, repairs, raw)

    def finalize(state: ReactionState) -> dict[str, Any]:
        if state.get("eligible") is True:
            return {}
        reason_raw = state.get("eligibility_reason")
        reason = reason_raw if isinstance(reason_raw, str) else "ineligible"
        return _no_reaction(reason, [], 0)

    def route(state: ReactionState) -> str:
        return "react" if state.get("eligible") is True else "skip"

    builder = StateGraph(ReactionState)
    builder.add_node("validate_eligibility", validate_eligibility)
    builder.add_node("render_prompts", render_prompts)
    builder.add_node("decide", decide)
    builder.add_node("finalize", finalize)
    builder.set_entry_point("validate_eligibility")
    builder.add_conditional_edges(
        "validate_eligibility", route, {"react": "render_prompts", "skip": "finalize"}
    )
    builder.add_edge("render_prompts", "decide")
    builder.add_edge("decide", "finalize")
    builder.set_finish_point("finalize")
    return builder.compile()


def _reaction_result(
    state: ReactionState,
    action: ActionIntent,
    errors: list[str],
    repairs: int,
    raw: str | None,
) -> dict[str, Any]:
    world_raw = state.get("world_id")
    scene_raw = state.get("scene_id")
    actor_raw = state.get("actor_id")
    attempt_raw = state.get("attempt_id")
    assert (
        isinstance(world_raw, str) and isinstance(actor_raw, str) and isinstance(attempt_raw, str)
    )
    reaction = Reaction(
        id=derive_reaction_id(UUID(attempt_raw), UUID(actor_raw)),
        world_id=UUID(world_raw),
        attempt_id=UUID(attempt_raw),
        scene_id=UUID(str(scene_raw)) if scene_raw else None,
        reactor_character_id=UUID(actor_raw),
        action=action,
    )
    return {
        "proposal": {
            "reaction": reaction.model_dump(mode="json"),
            "reacted": True,
            "reason": "valid",
        },
        "validation_errors": errors,
        "repair_count": repairs,
        "raw_response": raw,
        "status": "reacted",
    }


__all__ = [
    "REACTION_PROMPT_VERSION",
    "ReactionGraphDeps",
    "ReactionState",
    "build_reaction_graph",
    "check_eligibility",
    "load_reaction_prompt",
]
