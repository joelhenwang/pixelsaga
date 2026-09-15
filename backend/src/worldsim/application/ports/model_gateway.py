"""Provider-neutral model gateway port (owned by S0-MODEL-001).

Agents and orchestration depend on this protocol, never on provider SDKs.
Failures are normalized here so callers handle six cases, not HTTP details.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

AdapterName = Literal["fake", "openrouter"]


class ModelGatewayError(Exception):
    """Base for normalized model failures."""


class ModelTimeoutError(ModelGatewayError):
    pass


class ModelRateLimitedError(ModelGatewayError):
    def __init__(
        self, message: str = "model rate limited", retry_after_s: float | None = None
    ) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ModelUnavailableError(ModelGatewayError):
    pass


class ModelMalformedError(ModelGatewayError):
    pass


class ModelRefusalError(ModelGatewayError):
    pass


class ModelCapabilityError(ModelGatewayError):
    pass


class UnknownProfileError(LookupError):
    pass


class ModelProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=32)
    adapter: AdapterName
    model_id: str = Field(min_length=1, max_length=128)
    max_context_tokens: int = Field(default=8192, ge=1)
    capabilities: list[str] = Field(default_factory=list)


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str = Field(min_length=1, max_length=32000)
    max_tokens: int = Field(default=512, ge=1, le=4096)
    json_mode: bool = False


class CompletionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    model: str
    profile_version: str
    latency_ms: int = Field(ge=0)


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    texts: list[str] = Field(min_length=1, max_length=64)


class EmbeddingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    vectors: list[list[float]] = Field(min_length=1)
    model: str
    profile_version: str
    dimension: int = Field(ge=1)


class ProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    profile: str
    latency_ms: int = Field(ge=0)
    detail: str = ""


class ModelGateway(Protocol):
    profile: ModelProfile

    async def complete(self, request: CompletionRequest) -> CompletionResult: ...
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...
    async def probe(self) -> ProbeResult: ...
