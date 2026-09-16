"""OpenRouter adapter over plain HTTPS (owned by S0-MODEL-001).

No provider SDK is used: one httpx client talks to the OpenAI-compatible
endpoints, and every failure maps to the normalized gateway taxonomy.
"""

from __future__ import annotations

import time
from typing import Any, cast

import httpx
from pydantic import SecretStr

from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    CompletionResult,
    EmbeddingRequest,
    EmbeddingResult,
    ModelMalformedError,
    ModelProfile,
    ModelRateLimitedError,
    ModelRefusalError,
    ModelTimeoutError,
    ModelUnavailableError,
    ProbeResult,
)


def _retry_after_s(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


class OpenRouterGateway:
    def __init__(
        self,
        profile: ModelProfile,
        *,
        api_key: SecretStr,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_s: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.profile = profile
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._client = client
        self._owned_client = client is None

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}

    def _client_or_create(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=self._timeout_s)

    async def _close_owned(self, client: httpx.AsyncClient) -> None:
        if self._owned_client:
            await client.aclose()

    def _body(self, request: CompletionRequest) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        body: dict[str, Any] = {
            "model": self.profile.model_id,
            "messages": messages,
            "max_tokens": request.max_tokens,
        }
        if request.json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        client = self._client_or_create()
        started = time.monotonic()
        try:
            try:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=self._body(request),
                    headers=self._auth_headers(),
                )
            except httpx.TimeoutException as exc:
                raise ModelTimeoutError("openrouter request timed out") from exc
            except httpx.HTTPError as exc:
                raise ModelUnavailableError(f"openrouter transport failed: {exc}") from exc
            latency_ms = max(0, int((time.monotonic() - started) * 1000))
            return self._read_completion(response, latency_ms)
        finally:
            await self._close_owned(client)

    def _read_completion(self, response: httpx.Response, latency_ms: int) -> CompletionResult:
        if response.status_code == 429:
            raise ModelRateLimitedError(
                "openrouter rate limited", retry_after_s=_retry_after_s(response)
            )
        if response.status_code >= 400:
            raise ModelUnavailableError(
                f"openrouter rejected the request: HTTP {response.status_code}"
            )
        try:
            raw: Any = response.json()
        except ValueError as exc:
            raise ModelMalformedError("openrouter returned invalid JSON") from exc
        if not isinstance(raw, dict):
            raise ModelMalformedError("openrouter returned a non-object payload")
        payload = cast("dict[str, Any]", raw)
        choices_raw = payload.get("choices")
        if not isinstance(choices_raw, list) or not choices_raw:
            raise ModelMalformedError("openrouter response has no choices")
        choices = cast("list[Any]", choices_raw)
        choice_raw = choices[0]
        if not isinstance(choice_raw, dict):
            raise ModelMalformedError("openrouter response has no choices")
        choice = cast("dict[str, Any]", choice_raw)
        if choice.get("finish_reason") == "content_filter":
            raise ModelRefusalError("openrouter refused the prompt")
        message_raw = choice.get("message")
        if not isinstance(message_raw, dict):
            raise ModelMalformedError("openrouter response has no message")
        message = cast("dict[str, Any]", message_raw)
        text = message.get("content")
        if not isinstance(text, str) or not text:
            raise ModelMalformedError("openrouter response has no message text")
        usage_raw = payload.get("usage")
        usage: dict[str, Any]
        if isinstance(usage_raw, dict):
            usage = cast("dict[str, Any]", usage_raw)
        else:
            usage = {}
        model_raw = payload.get("model")
        model = model_raw if isinstance(model_raw, str) and model_raw else self.profile.model_id
        return CompletionResult(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            model=model,
            profile_version=self.profile.version,
            latency_ms=latency_ms,
        )

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        client = self._client_or_create()
        try:
            try:
                response = await client.post(
                    f"{self._base_url}/embeddings",
                    json={"model": self.profile.model_id, "input": request.texts},
                    headers=self._auth_headers(),
                )
            except httpx.TimeoutException as exc:
                raise ModelTimeoutError("openrouter request timed out") from exc
            except httpx.HTTPError as exc:
                raise ModelUnavailableError(f"openrouter transport failed: {exc}") from exc
            return self._read_embeddings(response)
        finally:
            await self._close_owned(client)

    def _read_embeddings(self, response: httpx.Response) -> EmbeddingResult:
        if response.status_code == 429:
            raise ModelRateLimitedError(
                "openrouter rate limited", retry_after_s=_retry_after_s(response)
            )
        if response.status_code >= 400:
            raise ModelUnavailableError(
                f"openrouter rejected the request: HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ModelMalformedError("openrouter returned invalid JSON") from exc
        try:
            vectors = [item["embedding"] for item in payload["data"]]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelMalformedError("openrouter embedding response has no data") from exc
        if not vectors or any(not isinstance(row, list) or not row for row in vectors):
            raise ModelMalformedError("openrouter embedding response has empty vectors")
        return EmbeddingResult(
            vectors=vectors,
            model=payload.get("model", self.profile.model_id),
            profile_version=self.profile.version,
            dimension=len(vectors[0]),
        )

    async def probe(self) -> ProbeResult:
        client = self._client_or_create()
        started = time.monotonic()
        try:
            try:
                response = await client.get(
                    f"{self._base_url}/models", headers=self._auth_headers()
                )
            except httpx.HTTPError as exc:
                return ProbeResult(
                    ok=False,
                    profile=f"{self.profile.name}@{self.profile.version}",
                    latency_ms=0,
                    detail=f"probe transport failed: {exc}",
                )
            latency_ms = max(0, int((time.monotonic() - started) * 1000))
            if response.status_code != 200:
                return ProbeResult(
                    ok=False,
                    profile=f"{self.profile.name}@{self.profile.version}",
                    latency_ms=latency_ms,
                    detail=f"probe HTTP {response.status_code}",
                )
            try:
                count = len(response.json().get("data", []))
            except ValueError:
                count = 0
            return ProbeResult(
                ok=True,
                profile=f"{self.profile.name}@{self.profile.version}",
                latency_ms=latency_ms,
                detail=f"{count} models listed",
            )
        finally:
            await self._close_owned(client)
