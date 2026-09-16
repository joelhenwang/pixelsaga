"""Director trigger, proposal, and validation contracts (owned by S2-DIRECTOR-001).

The Director proposes opportunities, never outcomes. A deterministic
trigger decides whether the model runs at all; a deterministic
validator decides whether its proposal lands. Requested powers
beyond the supported set (new NPCs, new locations) are rejected,
and permanent change (harm, death, rules) is not expressible.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.ids import ArcId, CharacterId, HookId, WorldId
from worldsim.domain.narrative import NarrativeArc, NarrativeHook

#: Phases between Director runs unless overridden in world config.
DIRECTOR_COOLDOWN_PHASES = 3
#: Caps enforced when accepting proposals.
MAX_ACTIVE_HOOKS = 3
MAX_ACTIVE_ARCS = 2
#: Powers a proposal may request. Anything else is rejected.
SUPPORTED_POWERS = frozenset({"spawn_npc", "new_location"})


class DirectorProposal(BaseModel):
    """One model-proposed opportunity (or an explicit no-op)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: str = Field(pattern="^(propose_hook|propose_arc|noop)$")
    title: str = Field(default="", max_length=128)
    purpose: str = Field(default="", max_length=1024)
    requested_powers: list[str] = Field(default_factory=list)
    participant_ids: list[CharacterId] = Field(default_factory=list)
    reason: str = Field(default="", max_length=512)


class DirectorDecision(BaseModel):
    """Validated outcome: accepted rows or a rejection reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: bool
    hook: NarrativeHook | None = None
    arc: NarrativeArc | None = None
    reason: str = Field(default="", max_length=512)


def should_trigger(
    absolute: int, last_absolute: int | None, cooldown: int = DIRECTOR_COOLDOWN_PHASES
) -> bool:
    """Run when the cooldown elapsed since the last attempt (never seen counts)."""
    if last_absolute is None:
        return True
    return absolute - last_absolute >= max(1, cooldown)


def validate_proposal(
    proposal: DirectorProposal,
    world_id: WorldId,
    known_character_ids: frozenset[CharacterId],
    active_hooks: int,
    active_arcs: int,
    hook_id: HookId,
    arc_id: ArcId,
) -> DirectorDecision:
    """Accept well-formed proposals inside privilege and budget; else reject."""
    if proposal.action == "noop":
        return DirectorDecision(accepted=False, reason=proposal.reason or "no-op")
    if not proposal.title.strip():
        return DirectorDecision(accepted=False, reason="proposals need a title")
    unknown = [p for p in proposal.requested_powers if p not in SUPPORTED_POWERS]
    if unknown:
        return DirectorDecision(
            accepted=False, reason=f"unsupported powers: {','.join(sorted(unknown))}"
        )
    strangers = [c for c in proposal.participant_ids if c not in known_character_ids]
    if strangers:
        return DirectorDecision(accepted=False, reason="participants must be known characters")
    if proposal.action == "propose_hook":
        if active_hooks >= MAX_ACTIVE_HOOKS:
            return DirectorDecision(accepted=False, reason="hook budget exhausted")
        return DirectorDecision(
            accepted=True,
            hook=NarrativeHook(
                id=hook_id,
                world_id=world_id,
                title=proposal.title.strip(),
                purpose=proposal.purpose,
                requested_powers=list(proposal.requested_powers),
                participant_ids=list(proposal.participant_ids),
            ),
        )
    if active_arcs >= MAX_ACTIVE_ARCS:
        return DirectorDecision(accepted=False, reason="arc budget exhausted")
    return DirectorDecision(
        accepted=True,
        arc=NarrativeArc(
            id=arc_id,
            world_id=world_id,
            title=proposal.title.strip(),
            purpose=proposal.purpose,
        ),
    )
