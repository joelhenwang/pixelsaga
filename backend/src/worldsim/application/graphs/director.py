# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""DirectorProposalGraph: bounded opportunity proposal (owned by S2-DIRECTOR-001).

START -> trigger check -> bounded omniscient context -> call Director
model -> validate shape, privileges, budgets -> one repair on schema
errors only -> proposal, rejection, or no-op -> END.

The trigger input (cooldown math) is computed deterministically by
the orchestrator and passed in as state: the graph never decides
when to run. Privilege and budget rejections are final; only
malformed JSON gets one repair. Model outage is a no-op, never a
phase failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from langgraph.graph import StateGraph
from pydantic import TypeAdapter, ValidationError

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
from worldsim.domain.director import DirectorProposal, validate_proposal

#: Versioned director prompt file.
DIRECTOR_PROMPT_VERSION = "director.v1"

_PROPOSAL_ADAPTER: TypeAdapter[DirectorProposal] = TypeAdapter(DirectorProposal)


class DirectorState(GraphState, total=False):
    """Graph state plus director-local trigger and budget fields."""

    decision: dict[str, Any] | None
    world_summary: str
    trigger_ok: bool
    trigger_reason: str
    known_character_ids: list[str]
    active_hooks: int
    active_arcs: int
    hook_id: str
    arc_id: str
    world_id: str
    system_prompt: str
    user_prompt: str
    raw_response: str | None


@dataclass(frozen=True)
class DirectorGraphDeps:
    """Everything the graph may call: a gateway and static text."""

    gateway: ModelGateway
    profile: ModelProfile
    system_template: str
    max_tokens: int = 512
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    repair_budget: int = 1


def prompt_path() -> Path:
    """Versioned prompt file next to the backend root."""
    return Path(__file__).resolve().parents[4] / "prompts" / f"{DIRECTOR_PROMPT_VERSION}.md"


def load_director_prompt() -> str:
    """Read the versioned director prompt (fails loudly when missing)."""
    return prompt_path().read_text(encoding="utf-8")


def render_user_prompt(world_summary: str) -> str:
    """Bounded omniscient context: counts, names, running hooks and arcs."""
    return (
        f"{world_summary}\n\n"
        "Propose at most one opportunity, or answer noop. "
        "Output exactly one JSON object matching the response schema."
    )


def _noop(reason: str, errors: list[str], repairs: int) -> dict[str, Any]:
    return {
        "proposal": None,
        "decision": {"accepted": False, "reason": reason},
        "validation_errors": errors,
        "repair_count": repairs,
        "raw_response": None,
        "status": "noop",
    }


def build_director_graph(deps: DirectorGraphDeps) -> Any:
    """Compile the bounded director graph around injected dependencies."""

    def check_trigger(state: DirectorState) -> dict[str, Any]:
        if state.get("trigger_ok") is True:
            return {"status": "triggered"}
        reason_raw = state.get("trigger_reason")
        reason = reason_raw if isinstance(reason_raw, str) else "cooldown active"
        return _noop(reason, [], 0)

    def render_prompts(state: DirectorState) -> dict[str, Any]:
        summary = state.get("world_summary")
        assert isinstance(summary, str) and summary
        return {
            "system_prompt": deps.system_template,
            "user_prompt": render_user_prompt(summary),
        }

    async def propose(state: DirectorState) -> dict[str, Any]:
        system = state.get("system_prompt")
        user = state.get("user_prompt")
        assert isinstance(system, str) and isinstance(user, str)
        errors: list[str] = []
        repairs = 0
        try:
            result = await deps.gateway.complete(
                CompletionRequest(
                    prompt=user,
                    system=system,
                    max_tokens=deps.max_tokens,
                    json_mode=True,
                    temperature=deps.temperature,
                    top_p=deps.top_p,
                    top_k=deps.top_k,
                )
            )
        except (
            ModelTimeoutError,
            ModelRateLimitedError,
            ModelUnavailableError,
            ModelRefusalError,
            ModelMalformedError,
        ) as exc:
            return _noop(f"provider failed ({type(exc).__name__})", [], 0)
        raw: str | None = result.text
        while True:
            try:
                proposal = _PROPOSAL_ADAPTER.validate_json(raw)
            except ValidationError as exc:
                errors.append(f"attempt {repairs}: {exc.error_count()} schema errors")
                if repairs >= deps.repair_budget:
                    return _noop(
                        f"unrepairable director output ({len(errors)} attempts)",
                        errors,
                        repairs,
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
                            temperature=deps.temperature,
                            top_p=deps.top_p,
                            top_k=deps.top_k,
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
                    return _noop(f"repair call failed ({type(exc).__name__})", errors, repairs)
                raw = repaired.text
                continue
            return _validate(state, proposal, errors, repairs, raw)

    def _validate(
        state: DirectorState,
        proposal: DirectorProposal,
        errors: list[str],
        repairs: int,
        raw: str | None,
    ) -> dict[str, Any]:
        world_raw = state.get("world_id")
        hook_raw = state.get("hook_id")
        arc_raw = state.get("arc_id")
        assert isinstance(world_raw, str) and world_raw
        assert isinstance(hook_raw, str) and hook_raw
        assert isinstance(arc_raw, str) and arc_raw
        known_raw = state.get("known_character_ids")
        assert isinstance(known_raw, list)
        hooks_raw = state.get("active_hooks")
        arcs_raw = state.get("active_arcs")
        assert isinstance(hooks_raw, int) and isinstance(arcs_raw, int)
        decision = validate_proposal(
            proposal,
            UUID(world_raw),
            frozenset(UUID(str(v)) for v in known_raw),
            hooks_raw,
            arcs_raw,
            UUID(hook_raw),
            UUID(arc_raw),
        )
        return {
            "proposal": proposal.model_dump(mode="json"),
            "decision": decision.model_dump(mode="json"),
            "validation_errors": errors,
            "repair_count": repairs,
            "raw_response": raw,
            "status": "proposed" if decision.accepted else "rejected",
        }

    def finalize(state: DirectorState) -> dict[str, Any]:
        if state.get("status") in ("triggered", None):
            return _noop("trigger evaluated without proposal", [], 0)
        return {}

    builder = StateGraph(DirectorState)
    builder.add_node("check_trigger", check_trigger)
    builder.add_node("render_prompts", render_prompts)
    builder.add_node("propose", propose)
    builder.add_node("finalize", finalize)
    builder.set_entry_point("check_trigger")

    def _route(state: DirectorState) -> str:
        if state.get("status") == "noop":
            return "finalize"
        return "render_prompts"

    builder.add_conditional_edges("check_trigger", _route)
    builder.add_edge("render_prompts", "propose")
    builder.add_edge("propose", "finalize")
    builder.set_finish_point("finalize")
    return builder.compile()
