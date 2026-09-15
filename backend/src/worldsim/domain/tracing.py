"""Model-call audit and context-manifest contracts (owned by S0-TRACE-001).

Every model interaction records a durable ``ModelCall`` row plus one
``ContextManifest`` describing exactly what the model was allowed to see.
Correlation IDs join the chain phase_run -> task_run -> model_call ->
context_manifest -> (later) world_event without any external service.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import CallStatus, Visibility
from worldsim.domain.ids import CallId, CharacterId, ManifestId, PhaseRunId, TaskId, WorldId

#: Policy version for the Stage 0 perspective filter (owner and
#: location scoping before any model sees a fact).
PERSPECTIVE_POLICY_V1 = "perspective-v1"


class ManifestSource(BaseModel):
    """One context section entry: included for a reason, or excluded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=256)
    kind: str = Field(min_length=1, max_length=64)
    owner_id: CharacterId | None = None
    visibility: Visibility
    score: float | None = None
    reason: str = Field(default="", max_length=512)


class ContextManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ManifestId
    call_id: CallId
    world_id: WorldId | None = None
    role: str = Field(min_length=1, max_length=64)
    perspective_policy: str = Field(default=PERSPECTIVE_POLICY_V1, max_length=64)
    profile_name: str = Field(min_length=1, max_length=64)
    profile_version: str = Field(min_length=1, max_length=32)
    prompt_version: str = Field(min_length=1, max_length=64)
    sources: list[ManifestSource] = Field(default_factory=list)
    budgets: dict[str, int] = Field(default_factory=dict)
    tokens: dict[str, int] = Field(default_factory=dict)
    dropped: list[str] = Field(default_factory=list)
    rendered_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ModelCall(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: CallId
    world_id: WorldId | None = None
    profile_name: str = Field(min_length=1, max_length=64)
    profile_version: str = Field(min_length=1, max_length=32)
    role: str = Field(min_length=1, max_length=64)
    phase_run_id: PhaseRunId | None = None
    task_run_id: TaskId | None = None
    actor_id: CharacterId | None = None
    status: CallStatus = CallStatus.STARTED
    prompt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    error_code: str | None = Field(default=None, max_length=64)
