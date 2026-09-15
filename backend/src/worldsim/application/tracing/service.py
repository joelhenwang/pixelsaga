"""Durable model-call audit around any gateway (owned by S0-TRACE-001).

Lifecycle per call: persist ``started`` row plus context manifest, run the
gateway with no open transaction, then persist the terminal row. Stored
prompts and completions pass through :func:`redact`, which masks API keys,
bearer tokens, connection strings, and credential assignments; raw secrets
must never land in ``model_call``, ``context_manifest``, or external export
payloads.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID, uuid4

from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    CompletionResult,
    ModelCapabilityError,
    ModelGatewayError,
    ModelMalformedError,
    ModelProfile,
    ModelRateLimitedError,
    ModelRefusalError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from worldsim.application.ports.traces import StoredCompletion, TraceExporter
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.enums import CallStatus
from worldsim.domain.tracing import ContextManifest, ManifestSource, ModelCall

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-[A-Za-z0-9\-_]{8,}"), "[REDACTED:api-key]"),
    (re.compile(r"[Bb]earer\s+[A-Za-z0-9\-._~+/=]+"), "[REDACTED:bearer]"),
    (
        re.compile(r"(?:postgresql|postgres|mysql|redis|sqlite)://[^\s'\"`]+"),
        "[REDACTED:connection-string]",
    ),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|secret|password|passwd|access[_-]?token|"
            r"auth[_-]?token|private[_-]?key)\b\s*[:=]\s*['\"]?[^\s'\"`,;}]+"
        ),
        r"\1=[REDACTED:credential]",
    ),
)


def redact(text: str) -> str:
    """Mask secret-like substrings; safe to run twice."""
    redacted = text
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def rendered_hash_for(prompt: str, profile: ModelProfile, prompt_version: str) -> str:
    """Deterministic hash binding prompt text to profile and prompt versions."""
    canonical = json.dumps(
        {
            "prompt": prompt,
            "profile": [profile.name, profile.version, profile.model_id],
            "prompt_version": prompt_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _error_code(exc: ModelGatewayError) -> str:
    if isinstance(exc, ModelTimeoutError):
        return "timeout"
    if isinstance(exc, ModelRateLimitedError):
        return "rate_limited"
    if isinstance(exc, ModelUnavailableError):
        return "unavailable"
    if isinstance(exc, ModelMalformedError):
        return "malformed"
    if isinstance(exc, ModelRefusalError):
        return "refusal"
    if isinstance(exc, ModelCapabilityError):
        return "capability"
    return "gateway_error"


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


@dataclass(frozen=True)
class ManifestSpec:
    """Caller-supplied manifest content; the service never widens scope."""

    role: str
    profile: ModelProfile
    prompt_version: str
    world_id: UUID | None = None
    phase_run_id: UUID | None = None
    task_run_id: UUID | None = None
    actor_id: UUID | None = None
    sources: list[ManifestSource] = field(default_factory=list)
    budgets: dict[str, int] = field(default_factory=dict)
    tokens: dict[str, int] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TracedCall:
    call_id: UUID
    manifest_id: UUID
    rendered_hash: str
    result: CompletionResult
    export_status: str
    export_detail: str


class TraceService:
    def __init__(self, uow_factory: UnitOfWorkFactory, exporter: TraceExporter) -> None:
        self._factory = uow_factory
        self._exporter = exporter

    async def run_call(
        self,
        spec: ManifestSpec,
        gateway: ModelGatewayLike,
        request: CompletionRequest,
    ) -> TracedCall:
        call_id = uuid4()
        manifest_id = uuid4()
        rendered = rendered_hash_for(request.prompt, spec.profile, spec.prompt_version)
        call = ModelCall(
            id=call_id,
            world_id=spec.world_id,
            profile_name=spec.profile.name,
            profile_version=spec.profile.version,
            role=spec.role,
            phase_run_id=spec.phase_run_id,
            task_run_id=spec.task_run_id,
            actor_id=spec.actor_id,
            prompt_hash=hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
        )
        manifest = ContextManifest(
            id=manifest_id,
            call_id=call_id,
            world_id=spec.world_id,
            role=spec.role,
            profile_name=spec.profile.name,
            profile_version=spec.profile.version,
            prompt_version=spec.prompt_version,
            sources=list(spec.sources),
            budgets=dict(spec.budgets),
            tokens=dict(spec.tokens),
            dropped=list(spec.dropped),
            rendered_hash=rendered,
        )
        async with self._factory() as uow:
            await uow.traces.ensure_profile(
                spec.profile.name,
                spec.profile.version,
                spec.profile.adapter,
                spec.profile.model_id,
                spec.profile.max_context_tokens,
                list(spec.profile.capabilities),
            )
            await uow.traces.start_call(
                call, redact(request.prompt), spec.prompt_version, request.max_tokens
            )
            await uow.traces.save_manifest(manifest)
            await uow.commit()

        started = time.perf_counter()
        try:
            result = await gateway.complete(request)
        except ModelGatewayError as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            failed = call.model_copy(
                update={
                    "status": CallStatus.FAILED,
                    "latency_ms": latency_ms,
                    "error_code": _error_code(exc),
                }
            )
            async with self._factory() as uow:
                await uow.traces.fail_call(call_id, _error_code(exc), latency_ms)
                await uow.commit()
            export = await self._exporter.export(failed, manifest, None)
            raise
        latency_ms = int((time.perf_counter() - started) * 1000)
        stored = StoredCompletion(
            text=redact(result.text),
            model=result.model,
            profile_version=result.profile_version,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            latency_ms=latency_ms,
        )
        finished = call.model_copy(
            update={
                "status": CallStatus.SUCCEEDED,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "latency_ms": latency_ms,
            }
        )
        async with self._factory() as uow:
            await uow.traces.finish_call(call_id, stored)
            await uow.commit()
        export = await self._exporter.export(finished, manifest, stored)
        return TracedCall(
            call_id=call_id,
            manifest_id=manifest_id,
            rendered_hash=rendered,
            result=result,
            export_status=export.status,
            export_detail=export.detail,
        )


class ModelGatewayLike(Protocol):
    profile: ModelProfile

    async def complete(self, request: CompletionRequest) -> CompletionResult: ...
