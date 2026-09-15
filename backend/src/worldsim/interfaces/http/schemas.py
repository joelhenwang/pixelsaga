"""Stage 0 request/response DTOs (owned by S0-API-001).

Never ORM structures: every model here is an explicit projection of a
domain record. UUIDs render as strings; operational timestamps are
ISO-8601 UTC.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import PhaseName


class HealthLiveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"] = "ok"


class DependencyCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    status: Literal["ok", "degraded", "failed"]
    detail: str = ""


class ReadyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready", "degraded"]
    version: str
    environment: str
    migration_head: str | None
    schema_version: int
    checks: list[DependencyCheck]


class WorldResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: str
    status: str
    day: int
    phase: PhaseName
    absolute_index: int
    seed_version: str
    version: int


class ClockResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    day: int
    phase: PhaseName
    absolute_index: int


class CurrentPhaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    absolute_index: int
    day: int
    phase: PhaseName
    run_id: UUID | None
    run_state: str | None


class EventEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int
    id: UUID
    event_type: str
    absolute_index: int
    phase_run_id: UUID
    effect_count: int


class EventsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entries: list[EventEntry]
    next_after: int


class SeedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    seed_version: str
    content_hash: str
    duplicate: bool


class AdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID


class AdvanceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    sequence: int


class AdvanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_id: UUID
    run_id: UUID
    task_id: UUID
    status: Literal["completed"] = "completed"
    world_version: int
    event_cursor: int
    idempotent_replay: bool
    result: AdvanceResult


class ReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID


class ReconcileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tasks_requeued: int
    outbox_requeued: int
    open_run_id: UUID | None
    open_state: str | None


class TaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    kind: str
    state: str
    owner: str | None
    attempt: int | None
    max_attempts: int | None
    expires_at: datetime | None


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    request_id: str
    details: dict[str, object] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    error: ErrorDetail
