# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""NarrationGraph: post-commit narration beats (owned by S1-NARRATE-001).

START -> validate post-commit gating -> render audience-scoped context
-> call narrator model -> validate beats against visible facts
-> repair once on unsupported facts -> structured-event fallback -> END.

Beats are linked presentation data: they cite committed fact keys and
source event IDs, never establish facts. The graph never touches
projections or repositories; the worker persists returned beats and
acks the narration outbox record. A missing or failed narrator falls
back to structured event text; canon never waits for prose.
"""

from __future__ import annotations

import json
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
from worldsim.domain.enums import NarrationKind
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_narration_id
from worldsim.domain.narration import BeatProposal, NarrationBeat

#: Versioned narrator prompt file.
NARRATOR_PROMPT_VERSION = "narrator.v1"

_BEATS_ADAPTER: TypeAdapter[list[BeatProposal]] = TypeAdapter(list[BeatProposal])


class NarrateState(GraphState, total=False):
    """Graph state plus narration-local gating and prompt fields."""

    event_id: str
    event_committed: bool
    audience_ids: list[str]
    visible_facts: list[dict[str, str]]
    beats_budget: int
    dnd_context: str | None
    system_prompt: str
    user_prompt: str
    raw_response: str | None


@dataclass(frozen=True)
class NarratorGraphDeps:
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
    return Path(__file__).resolve().parents[4] / "prompts" / f"{NARRATOR_PROMPT_VERSION}.md"


def load_narrator_prompt() -> str:
    """Read the versioned narrator prompt (fails loudly when missing)."""
    return prompt_path().read_text(encoding="utf-8")


def render_system_prompt(template: str) -> str:
    """Fill the response-schema placeholder (the only placeholder)."""
    schema_json = json.dumps(_BEATS_ADAPTER.json_schema(), indent=2, sort_keys=True)
    return template.replace("{{RESPONSE_SCHEMA}}", schema_json)


def render_user_prompt(
    audience_ids: list[str],
    visible_facts: list[dict[str, str]],
    event_id: str,
    scene_id: str | None,
    beats_budget: int,
    dnd_context: str | None = None,
) -> str:
    """Audience-scoped context: facts, event linkage, and beat budget."""
    lines = [
        f"Event {event_id}" + (f" in scene {scene_id}." if scene_id else "."),
        f"Audience: {', '.join(audience_ids) or 'none'}.",
        "Visible facts:",
        *[f"- {fact['key']}: {fact['value']}" for fact in visible_facts],
        f"Beat budget: {beats_budget}.",
    ]
    if dnd_context:
        lines.append(dnd_context)
    return "\n".join(lines)


def beats_valid(
    proposals: list[BeatProposal],
    *,
    visible_keys: frozenset[str],
    audience_ids: frozenset[str],
    beats_budget: int,
) -> str | None:
    """Unsupported-fact validator: cited keys, speakers, and budget."""
    if not proposals:
        return "narration needs at least one beat"
    if len(proposals) > beats_budget:
        return f"beat budget exceeded: {len(proposals)} > {beats_budget}"
    for proposal in proposals:
        unknown = set(proposal.cited_fact_keys) - visible_keys
        if unknown:
            return f"unsupported facts cited: {sorted(unknown)}"
        if not proposal.cited_fact_keys:
            return "every beat must cite at least one visible fact"
        if proposal.speaker_id is not None and str(proposal.speaker_id) not in audience_ids:
            return f"speaker outside the audience: {proposal.speaker_id}"
    return None


def fallback_beats(
    *,
    world_id: UUID,
    scene_id: UUID | None,
    event_id: UUID,
    visible_facts: list[dict[str, str]],
    beats_budget: int,
) -> list[NarrationBeat]:
    """Structured-event fallback: one beat per visible fact, budget-capped."""
    facts = visible_facts[: max(beats_budget, 1)]
    if not facts:
        return [
            NarrationBeat(
                id=new_narration_id(),
                world_id=world_id,
                scene_id=scene_id,
                source_event_id=event_id,
                kind=NarrationKind.NARRATION,
                text="Nothing of note occurs.",
            )
        ]
    return [
        NarrationBeat(
            id=new_narration_id(),
            world_id=world_id,
            scene_id=scene_id,
            source_event_id=event_id,
            cited_fact_keys=[fact["key"]],
            kind=NarrationKind.NARRATION,
            text=f"{fact['key']}: {fact['value']}",
        )
        for fact in facts
    ]


def stamp_beats(
    proposals: list[BeatProposal],
    *,
    world_id: UUID,
    scene_id: UUID | None,
    event_id: UUID,
) -> list[NarrationBeat]:
    """Stamp model proposals with ids and committed event linkage."""
    return [
        NarrationBeat(
            id=new_narration_id(),
            world_id=world_id,
            scene_id=scene_id,
            source_event_id=event_id,
            source_effect_ids=list(proposal.source_effect_ids),
            cited_fact_keys=list(proposal.cited_fact_keys),
            speaker_id=proposal.speaker_id,
            kind=proposal.kind,
            text=proposal.text,
            emotion_hint=proposal.emotion_hint,
        )
        for proposal in proposals
    ]


def build_narration_graph(deps: NarratorGraphDeps) -> Any:
    """Compile the post-commit narration graph around injected dependencies."""

    def validate_gating(state: NarrateState) -> dict[str, Any]:
        if state.get("event_committed") is not True:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, "narration starts after event commit")
        event_raw = state.get("event_id")
        if not isinstance(event_raw, str) or not event_raw:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, "narration needs an event")
        return {"status": "gating_valid"}

    def render_prompts(state: NarrateState) -> dict[str, Any]:
        event_raw = state.get("event_id")
        scene_raw = state.get("scene_id")
        audience_raw = state.get("audience_ids")
        facts_raw = state.get("visible_facts")
        budget_raw = state.get("beats_budget")
        assert isinstance(event_raw, str) and event_raw
        assert isinstance(audience_raw, list)
        assert isinstance(facts_raw, list)
        assert isinstance(budget_raw, int) and budget_raw >= 1
        return {
            "system_prompt": render_system_prompt(deps.system_template),
            "user_prompt": render_user_prompt(
                [str(a) for a in audience_raw],
                [{"key": str(f["key"]), "value": str(f["value"])} for f in facts_raw],
                event_raw,
                str(scene_raw) if scene_raw else None,
                budget_raw,
                state.get("dnd_context"),
            ),
        }

    async def decide(state: NarrateState) -> dict[str, Any]:
        system = state.get("system_prompt")
        user = state.get("user_prompt")
        assert isinstance(system, str) and isinstance(user, str)
        world_raw = state.get("world_id")
        event_raw = state.get("event_id")
        scene_raw = state.get("scene_id")
        assert isinstance(world_raw, str) and isinstance(event_raw, str)
        world_id, event_id = UUID(world_raw), UUID(event_raw)
        scene_id = UUID(str(scene_raw)) if scene_raw else None
        facts = [
            {"key": str(f["key"]), "value": str(f["value"])} for f in state.get("visible_facts", [])
        ]
        visible_keys = frozenset(f["key"] for f in facts)
        audience = frozenset(str(a) for a in state.get("audience_ids", []))
        budget_raw = state.get("beats_budget")
        budget = budget_raw if isinstance(budget_raw, int) else 8
        errors: list[str] = []
        repairs = 0
        try:
            result = await deps.gateway.complete(
                CompletionRequest(
                    prompt=user,
                    system=system,
                    max_tokens=deps.max_tokens,
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
            beats = fallback_beats(
                world_id=world_id,
                scene_id=scene_id,
                event_id=event_id,
                visible_facts=facts,
                beats_budget=budget,
            )
            return _narrated(
                state, beats, True, f"provider failed ({type(exc).__name__})", [], 0, None
            )
        raw: str | None = result.text
        while True:
            try:
                proposals = _BEATS_ADAPTER.validate_json(raw)
            except ValidationError as exc:
                errors.append(f"attempt {repairs}: {exc.error_count()} schema errors")
                if repairs >= deps.repair_budget:
                    return _fallback(
                        state, world_id, scene_id, event_id, facts, budget, errors, repairs, raw
                    )
                repairs += 1
                raw = await _repair_call(deps, system, user, errors[-1])
                if raw is None:
                    return _fallback(
                        state, world_id, scene_id, event_id, facts, budget, errors, repairs, None
                    )
                continue
            denial = beats_valid(
                proposals, visible_keys=visible_keys, audience_ids=audience, beats_budget=budget
            )
            if denial is not None:
                errors.append(f"attempt {repairs}: {denial}")
                if repairs >= deps.repair_budget:
                    return _fallback(
                        state, world_id, scene_id, event_id, facts, budget, errors, repairs, raw
                    )
                repairs += 1
                raw = await _repair_call(deps, system, user, denial)
                if raw is None:
                    return _fallback(
                        state, world_id, scene_id, event_id, facts, budget, errors, repairs, None
                    )
                continue
            beats = stamp_beats(proposals, world_id=world_id, scene_id=scene_id, event_id=event_id)
            return _narrated(state, beats, False, "valid", errors, repairs, raw)

    builder = StateGraph(NarrateState)
    builder.add_node("validate_gating", validate_gating)
    builder.add_node("render_prompts", render_prompts)
    builder.add_node("decide", decide)
    builder.set_entry_point("validate_gating")
    builder.add_edge("validate_gating", "render_prompts")
    builder.add_edge("render_prompts", "decide")
    builder.set_finish_point("decide")
    return builder.compile()


async def _repair_call(deps: NarratorGraphDeps, system: str, user: str, denial: str) -> str | None:
    """One bounded repair call; None when the provider fails."""
    try:
        repaired = await deps.gateway.complete(
            CompletionRequest(
                prompt=(
                    f"{user}\n\nYour previous output was rejected "
                    f"({denial}). Output a JSON array of beat objects "
                    "matching the response schema."
                ),
                system=system,
                max_tokens=deps.max_tokens,
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
    ):
        return None
    return repaired.text


def _beats_json(beats: list[NarrationBeat]) -> list[dict[str, Any]]:
    return [b.model_dump(mode="json") for b in beats]


def _narrated(
    state: NarrateState,
    beats: list[NarrationBeat],
    fallback: bool,
    reason: str,
    errors: list[str],
    repairs: int,
    raw: str | None,
) -> dict[str, Any]:
    return {
        "proposal": {
            "beats": _beats_json(beats),
            "fallback": fallback,
            "reason": reason,
        },
        "validation_errors": errors,
        "repair_count": repairs,
        "raw_response": raw,
        "status": "fallback" if fallback else "narrated",
    }


def _fallback(
    state: NarrateState,
    world_id: UUID,
    scene_id: UUID | None,
    event_id: UUID,
    facts: list[dict[str, str]],
    budget: int,
    errors: list[str],
    repairs: int,
    raw: str | None,
) -> dict[str, Any]:
    beats = fallback_beats(
        world_id=world_id,
        scene_id=scene_id,
        event_id=event_id,
        visible_facts=facts,
        beats_budget=budget,
    )
    return _narrated(state, beats, True, "structured-event fallback", errors, repairs, raw)


__all__ = [
    "NARRATOR_PROMPT_VERSION",
    "NarrateState",
    "NarratorGraphDeps",
    "beats_valid",
    "build_narration_graph",
    "fallback_beats",
    "load_narrator_prompt",
    "render_user_prompt",
    "stamp_beats",
]
