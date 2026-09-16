"""Scripted fake model adapter (owned by S0-MODEL-001).

Deterministic stand-in for the gateway protocol. Completion behavior is
fully scripted; embeddings are deterministic zeros; probe always succeeds.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    CompletionResult,
    EmbeddingRequest,
    EmbeddingResult,
    ModelGatewayError,
    ModelProfile,
    ProbeResult,
)


@dataclass
class ScriptedText:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class FakeGateway:
    profile: ModelProfile
    embedding_dim: int = 8
    default_text: str | None = None
    route: Callable[[CompletionRequest], str | ModelGatewayError | None] | None = None
    _script: deque[ScriptedText | ModelGatewayError] = field(default_factory=deque)
    _calls: list[str] = field(default_factory=list)
    _requests: list[CompletionRequest] = field(default_factory=list)

    def enqueue_text(self, text: str, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self._script.append(
            ScriptedText(
                text=text,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        )

    def enqueue_error(self, error: ModelGatewayError) -> None:
        self._script.append(error)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if self.route is not None:
            routed = self.route(request)
            if routed is not None:
                self._calls.append(request.prompt)
                self._requests.append(request)
                if isinstance(routed, ModelGatewayError):
                    raise routed
                return CompletionResult(
                    text=routed,
                    prompt_tokens=0,
                    completion_tokens=0,
                    model=self.profile.model_id,
                    profile_version=self.profile.version,
                    latency_ms=0,
                )
        if not self._script:
            if self.default_text is not None:
                self._calls.append(request.prompt)
                self._requests.append(request)
                return CompletionResult(
                    text=self.default_text,
                    prompt_tokens=0,
                    completion_tokens=0,
                    model=self.profile.model_id,
                    profile_version=self.profile.version,
                    latency_ms=0,
                )
            raise AssertionError("no scripted fake behavior; enqueue one first")
        item = self._script.popleft()
        self._calls.append(request.prompt)
        self._requests.append(request)
        if isinstance(item, ModelGatewayError):
            raise item
        return CompletionResult(
            text=item.text,
            prompt_tokens=item.prompt_tokens,
            completion_tokens=item.completion_tokens,
            model=self.profile.model_id,
            profile_version=self.profile.version,
            latency_ms=0,
        )

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        self._calls.append(f"embed:{len(request.texts)}")
        return EmbeddingResult(
            vectors=[[0.0] * self.embedding_dim for _ in request.texts],
            model=self.profile.model_id,
            profile_version=self.profile.version,
            dimension=self.embedding_dim,
        )

    async def probe(self) -> ProbeResult:
        return ProbeResult(
            ok=True,
            profile=f"{self.profile.name}@{self.profile.version}",
            latency_ms=0,
            detail="fake",
        )

    @property
    def calls(self) -> list[str]:
        return list(self._calls)

    @property
    def sent_requests(self) -> list[CompletionRequest]:
        return list(self._requests)

    def pending_count(self) -> int:
        return len(self._script)
