"""Durable natural-language intervention contracts (owned by REVAMP-P07).

Prompts never execute: the model proposes a bounded typed plan, the
server validates it against capabilities and world state, and a
durable queue applies it at a safe phase boundary with stable step
keys. Queued is not executed; starting travel is not arriving.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.ids import (
    CharacterId,
    InterventionId,
    InterventionStepId,
    LocationId,
    WorldId,
    new_intervention_id,
    new_intervention_step_id,
)


class InterventionMode(StrEnum):
    INFLUENCE = "influence"
    FORCE = "force"
    ATTEMPT = "attempt"


class InterventionStatus(StrEnum):
    INTERPRETING = "interpreting"
    NEEDS_CLARIFICATION = "needs_clarification"
    QUEUED = "queued"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIALLY_COMPLETED = "partially_completed"


class StepStatus(StrEnum):
    QUEUED = "queued"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepKind(StrEnum):
    PROPOSE_HOOK = "propose_hook"
    PROPOSE_ARC = "propose_arc"
    DIRECT_ACTIVITY = "direct_activity"
    DIRECT_ATTEMPT = "direct_attempt"
    OVERRIDE_CHARACTER = "override_character"


#: Attempt families with executable resolvers. Sparring is not hostile
#: combat: no family expresses lethal conflict, so fights stay explicit.
SUPPORTED_ATTEMPT_FAMILIES = frozenset(
    {"wait", "rest", "observe", "move", "communicate", "spar", "appeal", "transfer"}
)

#: Activity kinds the queue may start.
SUPPORTED_ACTIVITY_KINDS = frozenset({"travel", "rest", "train", "work", "patrol"})


class _StepBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    explanation: str = Field(default="", max_length=1024)


class ProposeHookStep(_StepBase):
    kind: Literal[StepKind.PROPOSE_HOOK] = StepKind.PROPOSE_HOOK
    title: str = Field(min_length=1, max_length=128)
    purpose: str = Field(default="", max_length=1024)
    participant_ids: list[CharacterId] = Field(default_factory=list)


class ProposeArcStep(_StepBase):
    kind: Literal[StepKind.PROPOSE_ARC] = StepKind.PROPOSE_ARC
    title: str = Field(min_length=1, max_length=128)
    purpose: str = Field(default="", max_length=1024)
    participant_ids: list[CharacterId] = Field(default_factory=list)


class DirectActivityStep(_StepBase):
    kind: Literal[StepKind.DIRECT_ACTIVITY] = StepKind.DIRECT_ACTIVITY
    character_id: CharacterId
    activity: str = Field(min_length=1, max_length=32)
    to_location_id: LocationId | None = None
    duration_phases: int | None = Field(default=None, ge=1, le=100)


class DirectAttemptStep(_StepBase):
    kind: Literal[StepKind.DIRECT_ATTEMPT] = StepKind.DIRECT_ATTEMPT
    character_id: CharacterId
    family: str = Field(min_length=1, max_length=32)
    action: dict[str, object] = Field(default_factory=dict)


class OverrideCharacterStep(_StepBase):
    kind: Literal[StepKind.OVERRIDE_CHARACTER] = StepKind.OVERRIDE_CHARACTER
    character_id: CharacterId
    stamina: int | None = Field(default=None, ge=0, le=100)
    mana: int | None = Field(default=None, ge=0, le=100)
    life_status: str | None = None
    conditions: list[str] = Field(default_factory=list)
    retcon: bool = False


InterpretationStep = Annotated[
    ProposeHookStep
    | ProposeArcStep
    | DirectActivityStep
    | DirectAttemptStep
    | OverrideCharacterStep,
    Field(discriminator="kind"),
]


class Interpretation(BaseModel):
    """One bounded model proposal: validated before anything is queued."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    steps: list[InterpretationStep] = Field(default_factory=list, max_length=5)
    clarification: str = Field(default="", max_length=1024)


class Intervention(BaseModel):
    id: InterventionId
    world_id: WorldId
    client_request_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=2000)
    mode: InterventionMode
    role: str = Field(min_length=1, max_length=16)
    status: InterventionStatus = InterventionStatus.QUEUED
    interpretation: Interpretation
    context_watermark: int = Field(default=0, ge=0)
    prompt_version: str = Field(default="intervene-v1", max_length=64)
    failure_reason: str = Field(default="", max_length=1024)
    version: int = Field(default=0, ge=0)


class InterventionStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: InterventionStepId
    intervention_id: InterventionId
    seq: int = Field(ge=0)
    step_key: str = Field(min_length=1, max_length=128)
    kind: StepKind
    targets: dict[str, object] = Field(default_factory=dict)
    status: StepStatus = StepStatus.QUEUED
    result_event_id: UUID | None = None
    result_activity_id: UUID | None = None
    result_hook_id: UUID | None = None
    failure_reason: str = Field(default="", max_length=1024)
    version: int = Field(default=0, ge=0)


def new_intervention_steps(
    intervention_id: InterventionId, steps: list[InterpretationStep]
) -> list[InterventionStep]:
    """Durable steps with stable keys derived from the intervention id."""
    return [
        InterventionStep(
            id=new_intervention_step_id(),
            intervention_id=intervention_id,
            seq=seq,
            step_key=f"{intervention_id.hex}:{seq}",
            kind=step.kind,
            targets=step.model_dump(mode="json", exclude={"kind", "explanation"}),
        )
        for seq, step in enumerate(steps)
    ]


__all__ = [
    "DirectActivityStep",
    "DirectAttemptStep",
    "Interpretation",
    "InterpretationStep",
    "Intervention",
    "InterventionMode",
    "InterventionStatus",
    "InterventionStep",
    "OverrideCharacterStep",
    "ProposeArcStep",
    "ProposeHookStep",
    "StepKind",
    "StepStatus",
    "SUPPORTED_ACTIVITY_KINDS",
    "SUPPORTED_ATTEMPT_FAMILIES",
    "new_intervention_id",
    "new_intervention_steps",
]
