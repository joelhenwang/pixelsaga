import ast
import asyncio
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    EmbeddingRequest,
    ModelCapabilityError,
    ModelGatewayError,
    ModelMalformedError,
    ModelRateLimitedError,
    ModelRefusalError,
    ModelTimeoutError,
    ModelUnavailableError,
    UnknownProfileError,
)
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.openrouter import OpenRouterGateway
from worldsim.infrastructure.model_gateway.probe import main as probe_main
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE, get_profile


def _fake() -> FakeGateway:
    return FakeGateway(profile=FAKE_TEST_PROFILE)


def test_fake_complete_success_records_usage() -> None:
    async def _inner() -> None:
        gateway = _fake()
        gateway.enqueue_text("hello there", prompt_tokens=3, completion_tokens=2)
        result = await gateway.complete(CompletionRequest(prompt="say hi"))
        assert result.text == "hello there"
        assert (result.prompt_tokens, result.completion_tokens) == (3, 2)
        assert result.profile_version == "test-v1"
        assert gateway.calls == ["say hi"]
        assert gateway.pending_count() == 0

    asyncio.run(_inner())


def test_fake_complete_replays_each_error_kind() -> None:
    async def _inner() -> None:
        gateway = _fake()
        gateway.enqueue_error(ModelTimeoutError())
        gateway.enqueue_error(ModelRateLimitedError(retry_after_s=7.0))
        gateway.enqueue_error(ModelMalformedError())
        gateway.enqueue_error(ModelRefusalError())
        gateway.enqueue_error(ModelUnavailableError())
        gateway.enqueue_error(ModelCapabilityError())
        with pytest.raises(ModelTimeoutError):
            await gateway.complete(CompletionRequest(prompt="a"))
        with pytest.raises(ModelRateLimitedError) as limited:
            await gateway.complete(CompletionRequest(prompt="b"))
        assert limited.value.retry_after_s == 7.0
        with pytest.raises(ModelMalformedError):
            await gateway.complete(CompletionRequest(prompt="c"))
        with pytest.raises(ModelRefusalError):
            await gateway.complete(CompletionRequest(prompt="d"))
        with pytest.raises(ModelUnavailableError):
            await gateway.complete(CompletionRequest(prompt="e"))
        with pytest.raises(ModelCapabilityError):
            await gateway.complete(CompletionRequest(prompt="f"))
        assert isinstance(limited.value, ModelGatewayError)

    asyncio.run(_inner())


def test_fake_embed_and_probe_are_deterministic() -> None:
    async def _inner() -> None:
        gateway = _fake()
        result = await gateway.embed(EmbeddingRequest(texts=["a", "b"]))
        assert result.dimension == 8
        assert result.vectors == [[0.0] * 8, [0.0] * 8]
        probe = await gateway.probe()
        assert probe.ok and probe.profile == "fake@test-v1"

    asyncio.run(_inner())


def _respond(response: httpx.Response) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return response

    return handler


def _mocked_gateway(
    handler: Callable[[httpx.Request], httpx.Response],
) -> OpenRouterGateway:
    profile = get_profile("openrouter", "chat-v1")
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return OpenRouterGateway(profile, api_key=SecretStr("test-sentinel-key"), client=client)


def test_openrouter_success_sends_auth_and_model() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "model": "openrouter/auto",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "once upon a phase"},
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 9},
            },
        )

    async def _inner() -> None:
        result = await _mocked_gateway(handler).complete(CompletionRequest(prompt="tell"))
        assert result.text == "once upon a phase"
        assert (result.prompt_tokens, result.completion_tokens) == (5, 9)

    asyncio.run(_inner())
    assert seen["auth"] == "Bearer test-sentinel-key"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "openrouter/auto"


def test_openrouter_rate_limit_reports_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(429, headers={"retry-after": "7"}, json={"error": "slow"})

    async def _inner() -> None:
        with pytest.raises(ModelRateLimitedError) as excinfo:
            await _mocked_gateway(handler).complete(CompletionRequest(prompt="x"))
        assert excinfo.value.retry_after_s == 7.0

    asyncio.run(_inner())


def test_openrouter_timeout_maps_to_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        raise httpx.TimeoutException("too slow")

    async def _inner() -> None:
        with pytest.raises(ModelTimeoutError):
            await _mocked_gateway(handler).complete(CompletionRequest(prompt="x"))

    asyncio.run(_inner())


def test_openrouter_malformed_and_refusal_and_unavailable() -> None:
    async def _inner() -> None:
        bad_json = _mocked_gateway(_respond(httpx.Response(200, content=b"nope{")))
        with pytest.raises(ModelMalformedError):
            await bad_json.complete(CompletionRequest(prompt="x"))
        no_choices = _mocked_gateway(_respond(httpx.Response(200, json={"choices": []})))
        with pytest.raises(ModelMalformedError):
            await no_choices.complete(CompletionRequest(prompt="x"))
        refused = _mocked_gateway(
            _respond(
                httpx.Response(
                    200,
                    json={
                        "choices": [{"finish_reason": "content_filter", "message": {"content": ""}}]
                    },
                )
            )
        )
        with pytest.raises(ModelRefusalError):
            await refused.complete(CompletionRequest(prompt="x"))
        broken = _mocked_gateway(_respond(httpx.Response(500, json={})))
        with pytest.raises(ModelUnavailableError):
            await broken.complete(CompletionRequest(prompt="x"))

    asyncio.run(_inner())


def test_profiles_are_versioned_and_lookup_fails_cleanly() -> None:
    assert get_profile("fake", "test-v1").adapter == "fake"
    assert get_profile("openrouter", "embed-v1").adapter == "openrouter"
    with pytest.raises(UnknownProfileError):
        get_profile("openrouter", "nope-v9")


def test_live_probe_refuses_without_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORLDSIM_MODEL_LIVE_PROBE", raising=False)
    assert probe_main([]) == 2


def test_ports_import_only_contracts() -> None:
    """Ports may use stdlib, Pydantic, and domain contracts only: never
    infrastructure, interfaces, agents, providers, or persistence."""
    stdlib = set(__import__("sys").stdlib_module_names)
    ports = Path(__file__).parent.parent / "src" / "worldsim" / "application" / "ports"
    violations: list[str] = []

    def _allowed(module: str) -> bool:
        top = module.split(".")[0]
        if top in stdlib or top == "pydantic":
            return True
        return module == "worldsim.domain" or module.startswith("worldsim.domain.")

    for path in sorted(ports.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not _allowed(alias.name):
                        violations.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    violations.append(f"{path.name}: relative import")
                    continue
                if not _allowed(node.module or ""):
                    violations.append(f"{path.name}: from {node.module}")
    assert violations == []
