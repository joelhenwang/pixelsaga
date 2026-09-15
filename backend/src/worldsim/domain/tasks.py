"""Task-run, lease, and outbox contracts (owned by S0-DOM-001).

Kind is an explicit slug (Stage 0 uses ``phase_advance``); behavior and
retry budgets belong to the application services.
"""

from __future__ import annotations

from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from worldsim.domain.enums import OutboxState, TaskRunState
from worldsim.domain.ids import EventId, OutboxId, TaskId, WorldId
from worldsim.domain.time import utcnow

Slug = str

PHASE_ADVANCE_TASK = "phase_advance"


class Lease(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    owner: str = Field(min_length=1, max_length=128)
    claimed_at: AwareDatetime = Field(default_factory=utcnow)
    expires_at: AwareDatetime
    attempt: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    input_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


class TaskRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: TaskId
    world_id: WorldId
    kind: Slug = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    state: TaskRunState = TaskRunState.PENDING
    lease: Lease | None = None
    created_at: AwareDatetime = Field(default_factory=utcnow)
    updated_at: AwareDatetime = Field(default_factory=utcnow)


class OutboxMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: OutboxId
    world_id: WorldId
    event_id: EventId | None = None
    kind: Slug = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=128)
    state: OutboxState = OutboxState.PENDING
    created_at: AwareDatetime = Field(default_factory=utcnow)
