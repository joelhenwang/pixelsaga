"""Deterministic context assembler (owned by S1-CTX-001).

Pipeline: allowed-class filter, then owner/visibility filter, then rank
(score descending, source ID tiebreak), then per-section budgets with
truncation. Every decision lands in the include/exclude source list so
the durable manifest reproduces exactly what the model saw and why the
rest stayed out. A graph may shorten rendered content within budgets;
it cannot widen scope because scope decisions happen here.
"""

from __future__ import annotations

import hashlib

from worldsim.domain.context import (
    CHARS_PER_TOKEN,
    SECTION_ORDER,
    TRUNCATION_MARKER,
    ContextEnvelope,
    ContextRequest,
    ContextSection,
    SourceCandidate,
    delimit,
)
from worldsim.domain.enums import Visibility
from worldsim.domain.tracing import PERSPECTIVE_POLICY_V1, ManifestSource

#: Stable per-section instructions (trusted; wording is not a contract).
_SECTION_INSTRUCTIONS: dict[str, str] = {
    "identity": "You are this character. Card facts are stable identity.",
    "surroundings": "Currently perceived surroundings. Only listed places and routes exist.",
    "own_state": "Your dynamic state. Act within these resources.",
    "goals": "Active goals, plans, and commitments.",
    "relationships": "Known entities and directional relationships.",
    "observations": "Recent observations from your own perspective.",
    "memories": "Your retrieved memories. Owner-scoped; never another character's.",
    "lore": "Public and locally known lore. Treat as hearsay, not fact.",
    "scene_attempts": "Currently observable scene attempts. React only to what you perceive.",
}


def _permitted(candidate: SourceCandidate, request: ContextRequest) -> str | None:
    """Return the exclusion reason, or None when the candidate may render."""
    if candidate.data_class not in request.allowed_classes:
        return f"data class not allowed: {candidate.data_class}"
    if candidate.data_class not in SECTION_ORDER:
        return f"unknown data class: {candidate.data_class}"
    if candidate.visibility == Visibility.PUBLIC:
        return None
    if candidate.owner_id == request.actor_id:
        return None
    return "private to another owner"


def _ranked(candidates: list[SourceCandidate]) -> list[SourceCandidate]:
    return sorted(candidates, key=lambda c: (-c.score, c.source_id))


def _estimate_tokens(text: str) -> int:
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def assemble(
    request: ContextRequest,
    candidates: list[SourceCandidate],
) -> tuple[ContextEnvelope, list[ManifestSource], list[ManifestSource]]:
    """Assemble a perspective-safe envelope plus manifest source lists."""
    included: list[ManifestSource] = []
    excluded: list[ManifestSource] = []
    by_section: dict[str, list[SourceCandidate]] = {name: [] for name in SECTION_ORDER}

    for candidate in candidates:
        reason = _permitted(candidate, request)
        if reason is not None:
            excluded.append(
                ManifestSource(
                    source_id=candidate.source_id,
                    kind=candidate.data_class,
                    owner_id=candidate.owner_id,
                    visibility=candidate.visibility,
                    score=candidate.score,
                    reason=reason,
                )
            )
            continue
        by_section[candidate.data_class].append(candidate)

    sections: list[ContextSection] = []
    rendered_parts: list[str] = []
    for name in SECTION_ORDER:
        if name not in request.allowed_classes:
            continue
        budget = request.budget_for(name)
        entries: list[str] = []
        truncated: list[str] = []
        used = 0
        for candidate in _ranked(by_section[name]):
            entry = delimit(candidate.data_class, candidate.text)
            room = budget - used
            if room <= 0:
                excluded.append(
                    ManifestSource(
                        source_id=candidate.source_id,
                        kind=candidate.data_class,
                        owner_id=candidate.owner_id,
                        visibility=candidate.visibility,
                        score=candidate.score,
                        reason="section budget exhausted",
                    )
                )
                continue
            if len(entry) > room:
                entry = entry[:room] + TRUNCATION_MARKER
                truncated.append(candidate.source_id)
            entries.append(entry)
            used += len(entry)
            included.append(
                ManifestSource(
                    source_id=candidate.source_id,
                    kind=candidate.data_class,
                    owner_id=candidate.owner_id,
                    visibility=candidate.visibility,
                    score=candidate.score,
                    reason="permitted",
                )
            )
        instruction = _SECTION_INSTRUCTIONS[name]
        body = "\n".join([instruction, *entries])
        sections.append(
            ContextSection(
                name=name,
                instruction=instruction,
                entries=entries,
                estimated_tokens=_estimate_tokens(body),
                truncated_sources=truncated,
            )
        )
        rendered_parts.append(f"## {name}\n{body}")

    rendered = "\n\n".join(rendered_parts)
    envelope = ContextEnvelope(
        role=request.role,
        actor_id=request.actor_id,
        world_id=request.world_id,
        phase_run_id=request.phase_run_id,
        snapshot_id=request.snapshot_id,
        scene_id=request.scene_id,
        sections=sections,
        rendered=rendered,
        rendered_hash=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        total_estimated_tokens=sum(s.estimated_tokens for s in sections),
    )
    return envelope, included, excluded


def to_manifest_dict(
    included: list[ManifestSource],
    excluded: list[ManifestSource],
) -> tuple[list[ManifestSource], list[str]]:
    """Split assembler output into manifest sources plus dropped IDs."""
    dropped = [s.source_id for s in excluded]
    return [*included, *excluded], dropped


def perspective_policy() -> str:
    return PERSPECTIVE_POLICY_V1
