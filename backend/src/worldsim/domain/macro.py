"""Macro simulation and genealogy contracts (owned by S5-CONTRACT-001).

A macro period run advances a quiet interval at reduced resolution
(day/week/month/year) without per-phase model calls. Its result must
decompose into sourced, typed aggregate effects, each linked to exactly
one canonical event, so every state change keeps event/effect
provenance across resolution levels.

Genealogy records parent/child links with fictional birth positions
and explicit focus succession. By design there is no memory field on
any lineage record: private memories never transfer to descendants
without an explicit lore mechanism, which is a later-stage rule, not
a contract default.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from worldsim.domain.enums import (
    EndConditionKind,
    FocusSlot,
    InterruptionReason,
    LifeStatus,
    MacroEffectKind,
    MacroResolution,
    MacroRunState,
)
from worldsim.domain.ids import (
    CharacterId,
    EndEvidenceId,
    EraSummaryId,
    EventId,
    FocusAssignmentId,
    LineageLinkId,
    MacroAggregateEffectId,
    MacroInterruptionId,
    MacroRunId,
    WorldId,
)
from worldsim.domain.time import PHASES_PER_DAY

DAYS_PER_WEEK = 7
DAYS_PER_MONTH = 30
DAYS_PER_YEAR = 360

RESOLUTION_DAYS: dict[MacroResolution, int] = {
    MacroResolution.DAY: 1,
    MacroResolution.WEEK: DAYS_PER_WEEK,
    MacroResolution.MONTH: DAYS_PER_MONTH,
    MacroResolution.YEAR: DAYS_PER_YEAR,
}


def resolution_range(day: int, resolution: MacroResolution) -> tuple[int, int]:
    """Absolute phase bounds for a 1-based day at a resolution, end exclusive."""
    if day < 1:
        raise ValueError("day starts at 1")
    days = RESOLUTION_DAYS[resolution]
    start_day = ((day - 1) // days) * days + 1
    start = (start_day - 1) * PHASES_PER_DAY
    return start, start + days * PHASES_PER_DAY


class MacroPeriodRun(BaseModel):
    """One deterministic advance of a quiet interval at reduced resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: MacroRunId
    world_id: WorldId
    start_absolute: int = Field(ge=0)
    end_absolute: int = Field(ge=0)
    resolution: MacroResolution
    state: MacroRunState = MacroRunState.PLANNED
    seed: int = Field(ge=0)
    version: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _exclusive_end_after_start(self) -> MacroPeriodRun:
        if self.end_absolute <= self.start_absolute:
            raise ValueError("end_absolute must be past start_absolute")
        return self

    def contains(self, absolute: int) -> bool:
        return self.start_absolute <= absolute < self.end_absolute


class MacroAggregateEffect(BaseModel):
    """One sourced aggregate change produced by a macro run.

    The engine decomposes each record into concrete row updates and
    commits exactly one canonical event per record; ``event_id`` is
    that event once committed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: MacroAggregateEffectId
    run_id: MacroRunId
    world_id: WorldId
    kind: MacroEffectKind
    target_ids: list[CharacterId] = Field(default_factory=list, max_length=64)
    detail: str = Field(min_length=1, max_length=2000)
    event_id: EventId | None = None


class MacroInterruption(BaseModel):
    """A high-salience break that returns a macro run to detailed simulation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: MacroInterruptionId
    run_id: MacroRunId
    world_id: WorldId
    at_absolute: int = Field(ge=0)
    reason: InterruptionReason
    detail: str = Field(min_length=1, max_length=2000)


class LineageLink(BaseModel):
    """One parent-to-child link with a fictional birth position."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: LineageLinkId
    world_id: WorldId
    parent_id: CharacterId
    child_id: CharacterId
    birth_absolute: int = Field(ge=0)

    @model_validator(mode="after")
    def _distinct_ends(self) -> LineageLink:
        if self.parent_id == self.child_id:
            raise ValueError("parent and child must differ")
        return self


class LineageCharacter(BaseModel):
    """Genealogy projection of one character: birth, death, succession.

    Carries no memories. Public history stays attached to the entity
    ID; descendants start with no inherited private records.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: CharacterId
    world_id: WorldId
    birth_absolute: int = Field(ge=0)
    death_absolute: int | None = None
    life_status: LifeStatus = LifeStatus.ALIVE
    succession_eligible: bool = False

    @model_validator(mode="after")
    def _death_after_birth(self) -> LineageCharacter:
        if self.death_absolute is not None and self.death_absolute < self.birth_absolute:
            raise ValueError("death_absolute cannot precede birth_absolute")
        return self


class FocusAssignment(BaseModel):
    """Explicit, versioned focus-slot succession between characters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: FocusAssignmentId
    world_id: WorldId
    slot: FocusSlot
    from_character_id: CharacterId | None = None
    to_character_id: CharacterId
    effective_absolute: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)
    version: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _succession_changes_holder(self) -> FocusAssignment:
        if self.from_character_id is not None and self.from_character_id == self.to_character_id:
            raise ValueError("succession must change the holder")
        return self


class EraSummary(BaseModel):
    """One version of one owner's account of a macro interval.

    Same accumulation rule as daily summaries: regeneration writes a
    new row, never rewrites; source IDs point at macro events and
    perspective-owned records only.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: EraSummaryId
    world_id: WorldId
    owner_id: CharacterId
    start_absolute: int = Field(ge=0)
    end_absolute: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=8000)
    source_ids: list[str] = Field(default_factory=list)
    profile_version: str = Field(default="", max_length=64)
    prompt_version: str = Field(default="", max_length=64)
    fallback: bool = False
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _exclusive_end_after_start(self) -> EraSummary:
        if self.end_absolute <= self.start_absolute:
            raise ValueError("end_absolute must be past start_absolute")
        return self


class EndConditionEvidence(BaseModel):
    """Deterministic evidence for one end-condition evaluation.

    One calm scene never satisfies peace: ``window_start_absolute``
    bounds the sustained window the evaluation inspected, and
    ``evidence_event_ids`` carries the supporting canon.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: EndEvidenceId
    world_id: WorldId
    kind: EndConditionKind
    evaluated_absolute: int = Field(ge=0)
    window_start_absolute: int = Field(ge=0)
    satisfied: bool = False
    evidence_event_ids: list[EventId] = Field(default_factory=list)
    detail: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _window_within_evaluation(self) -> EndConditionEvidence:
        if self.window_start_absolute > self.evaluated_absolute:
            raise ValueError("window_start_absolute cannot pass evaluated_absolute")
        return self
