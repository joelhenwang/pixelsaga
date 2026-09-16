"""Traced gateway decorator (owned by S1-ORCH-001).

Wraps any model gateway so every completion the graphs perform lands
in the durable audit chain (phase run, task run, actor, context
manifest, model call) through ``TraceService``. The decorator adds no
scope: the manifest sources are exactly the assembler's include/exclude
lists, and failures still raise the normalized gateway taxonomy after
the failed call is recorded.
"""

from __future__ import annotations

from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    CompletionResult,
    EmbeddingRequest,
    EmbeddingResult,
    ModelGateway,
    ModelProfile,
    ProbeResult,
)
from worldsim.application.tracing.service import ManifestSpec, TracedCall, TraceService


class TracedGateway:
    """ModelGateway that audits every completion via the trace service."""

    profile: ModelProfile

    def __init__(
        self,
        inner: ModelGateway,
        traces: TraceService,
        spec: ManifestSpec,
    ) -> None:
        self._inner = inner
        self._traces = traces
        self._spec = spec
        self.profile = inner.profile
        self.calls: list[TracedCall] = []

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        traced = await self._traces.run_call(self._spec, self._inner, request)
        self.calls.append(traced)
        return traced.result

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        return await self._inner.embed(request)

    async def probe(self) -> ProbeResult:
        return await self._inner.probe()


__all__ = ["TracedGateway"]
