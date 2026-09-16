# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""SummaryGraph: bounded daily retelling (owned by S2-SUMMARY-001).

START -> render owner sources -> call summary model -> validate
cited sources are a subset of inputs, text within budget -> one
repair on schema errors -> proposal, rejection, or fallback -> END.

The graph proposes presentation only. Source rows are never read
for writing here and are never modified anywhere in this path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.graph import StateGraph
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

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

#: Versioned summary prompt file.
SUMMARY_PROMPT_VERSION = "summary.v1"

#: Versioned digest prompt file; same graph, different task.
DIGEST_PROMPT_VERSION = "digest.v1"

#: Model output budget for one day's retelling.
SUMMARY_MAX_CHARS = 4000


class SummaryProposal(BaseModel):
    """One model-proposed retelling with cited sources."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=SUMMARY_MAX_CHARS)
    source_ids: list[str] = Field(default_factory=list)


_PROPOSAL_ADAPTER: TypeAdapter[SummaryProposal] = TypeAdapter(SummaryProposal)


class SummaryState(GraphState, total=False):
    """Graph state plus summary-local source fields."""

    fallback: bool
    fallback_reason: str
    owner_name: str
    day: int
    sources_text: str
    source_ids: list[str]
    system_prompt: str
    user_prompt: str
    raw_response: str | None


@dataclass(frozen=True)
class SummaryGraphDeps:
    """Everything the graph may call: a gateway and static text."""

    gateway: ModelGateway
    profile: ModelProfile
    system_template: str
    max_tokens: int = 512
    repair_budget: int = 1


def prompt_path() -> Path:
    """Versioned prompt file next to the backend root."""
    return Path(__file__).resolve().parents[4] / "prompts" / f"{SUMMARY_PROMPT_VERSION}.md"


def load_summary_prompt() -> str:
    """Read the versioned summary prompt (fails loudly when missing)."""
    return prompt_path().read_text(encoding="utf-8")


def load_digest_prompt() -> str:
    """Read the versioned digest prompt (fails loudly when missing)."""
    path = Path(__file__).resolve().parents[4] / "prompts" / f"{DIGEST_PROMPT_VERSION}.md"
    return path.read_text(encoding="utf-8")


def render_user_prompt(owner_name: str, day: int, sources_text: str) -> str:
    """Owner sources with stable IDs; nothing else enters."""
    return (
        f"{owner_name}'s sources for day {day}:\n{sources_text}\n\n"
        "Retell this day from these sources only. "
        "Output exactly one JSON object matching the response schema."
    )


def _fallback(reason: str, errors: list[str], repairs: int) -> dict[str, Any]:
    return {
        "proposal": None,
        "fallback": True,
        "fallback_reason": reason,
        "validation_errors": errors,
        "repair_count": repairs,
        "raw_response": None,
        "status": "fallback",
    }


def build_summary_graph(deps: SummaryGraphDeps) -> Any:
    """Compile the bounded summary graph around injected dependencies."""

    def render_prompts(state: SummaryState) -> dict[str, Any]:
        name = state.get("owner_name")
        day = state.get("day")
        sources = state.get("sources_text")
        assert isinstance(name, str) and name
        assert isinstance(day, int)
        assert isinstance(sources, str) and sources
        return {
            "system_prompt": deps.system_template,
            "user_prompt": render_user_prompt(name, day, sources),
        }

    async def propose(state: SummaryState) -> dict[str, Any]:
        system = state.get("system_prompt")
        user = state.get("user_prompt")
        assert isinstance(system, str) and isinstance(user, str)
        allowed_raw = state.get("source_ids")
        assert isinstance(allowed_raw, list)
        allowed = {str(v) for v in allowed_raw}
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
            return _fallback(f"provider failed ({type(exc).__name__})", [], 0)
        raw: str | None = result.text
        while True:
            try:
                proposal = _PROPOSAL_ADAPTER.validate_json(raw)
            except ValidationError as exc:
                errors.append(f"attempt {repairs}: {exc.error_count()} schema errors")
                if repairs >= deps.repair_budget:
                    return _fallback(
                        f"unrepairable summary output ({len(errors)} attempts)",
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
                    return _fallback(
                        f"repair call failed ({type(exc).__name__})",
                        errors,
                        repairs,
                    )
                raw = repaired.text
                continue
            unknown = [s for s in proposal.source_ids if s not in allowed]
            if unknown:
                return _fallback(
                    f"cited unknown sources: {','.join(sorted(unknown))}",
                    errors,
                    repairs,
                )
            return {
                "proposal": proposal.model_dump(mode="json"),
                "fallback": False,
                "fallback_reason": "",
                "validation_errors": errors,
                "repair_count": repairs,
                "raw_response": raw,
                "status": "proposed",
            }

    builder = StateGraph(SummaryState)
    builder.add_node("render_prompts", render_prompts)
    builder.add_node("propose", propose)
    builder.set_entry_point("render_prompts")
    builder.add_edge("render_prompts", "propose")
    builder.set_finish_point("propose")
    return builder.compile()
