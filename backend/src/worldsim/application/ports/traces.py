"""Context-manifest and model-call persistence ports (owned by S0-TRACE-001).

Correlation IDs (phase/task/actor) are first-class columns so the audit
chain joins without an external service. Request/response bodies stay in
JSONB; the service redacts them before they reach any adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.tracing import ContextManifest, ModelCall

ExportStatus = Literal["ok", "skipped", "failed"]


class TraceRepository(Protocol):
    async def ensure_profile(
        self,
        name: str,
        version: str,
        adapter: str,
        model_id: str,
        max_context_tokens: int,
        capabilities: list[str],
    ) -> None: ...

    async def start_call(
        self,
        call: ModelCall,
        prompt_redacted: str,
        prompt_version: str,
        max_tokens: int,
    ) -> None: ...

    async def finish_call(self, call_id: UUID, completion: StoredCompletion) -> None: ...

    async def fail_call(self, call_id: UUID, error_code: str, latency_ms: int) -> None: ...

    async def save_manifest(self, manifest: ContextManifest) -> None: ...

    async def get_call(self, call_id: UUID) -> ModelCall: ...

    async def get_manifest(self, call_id: UUID) -> ContextManifest: ...

    async def list_for_phase_run(self, phase_run_id: UUID) -> list[ModelCall]: ...


class StoredCompletion(BaseModel):
    """Redacted completion stored and exported; built by the trace service."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    model: str = Field(min_length=1, max_length=128)
    profile_version: str = Field(min_length=1, max_length=32)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)


@dataclass(frozen=True)
class ExportResult:
    status: ExportStatus
    detail: str


class TraceExporter(Protocol):
    """Optional external trace sink. Never canonical; never raises."""

    async def export(
        self, call: ModelCall, manifest: ContextManifest, completion: StoredCompletion | None
    ) -> ExportResult: ...
