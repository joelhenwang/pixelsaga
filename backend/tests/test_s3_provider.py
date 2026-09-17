"""Stage 3 provider selection, retry, and cost tests (owned by S3-PROV-001)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    CompletionResult,
    ModelProfile,
    ModelRateLimitedError,
    ModelRefusalError,
)
from worldsim.domain.costs import PRICING_VERSION, compute_cost
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.model_gateway.retry import RetryingGateway
from worldsim.infrastructure.model_gateway.selection import gateways_for_settings
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"

WORLD_ID = UUID("10000000-0000-4000-8000-000000000001")
WREN_ID = UUID("10000000-0000-4000-8000-000000000101")
ASH_ID = UUID("10000000-0000-4000-8000-000000000102")
PLACEHOLDER_SNAPSHOT = "00000000-0000-4000-8000-000000000000"


class ScriptedGateway:
    """Failing-then-passing gateway with a call count for retry tests."""

    def __init__(self, profile: ModelProfile, behaviors: list[Any]) -> None:
        self.profile = profile
        self._behaviors = behaviors
        self.calls = 0

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls += 1
        behavior = self._behaviors[min(self.calls - 1, len(self._behaviors) - 1)]
        if isinstance(behavior, Exception):
            raise behavior
        return behavior

    async def embed(self, request: Any) -> Any:
        raise AssertionError("embed unused in retry tests")

    async def probe(self) -> Any:
        raise AssertionError("probe unused in retry tests")


def _result() -> CompletionResult:
    return CompletionResult(
        text='{"ok": true}',
        prompt_tokens=10,
        completion_tokens=5,
        model="openai/gpt-4o-mini",
        profile_version="chat-v1",
        latency_ms=1,
    )


def _request() -> CompletionRequest:
    return CompletionRequest(prompt="hello", system="You decide", max_tokens=16)


def test_retry_honors_rate_limit_then_succeeds() -> None:
    inner = ScriptedGateway(
        FAKE_TEST_PROFILE,
        [ModelRateLimitedError("slow", retry_after_s=5.0), _result()],
    )
    sleeps: list[float] = []

    async def _sleep(delay: float) -> None:
        sleeps.append(delay)

    gateway = RetryingGateway(inner, sleep=_sleep)
    result = asyncio.run(gateway.complete(_request()))
    assert result.text == '{"ok": true}'
    assert inner.calls == 2
    assert sleeps == [5.0]


def test_retry_exhausts_and_raises_last() -> None:
    inner = ScriptedGateway(
        FAKE_TEST_PROFILE, [ModelRateLimitedError("slow", retry_after_s=120.0)]
    )
    gateway = RetryingGateway(inner, max_attempts=2, sleep=_ignore_sleep)
    with pytest.raises(ModelRateLimitedError):
        asyncio.run(gateway.complete(_request()))
    assert inner.calls == 2


async def _ignore_sleep(delay: float) -> None:
    return None


def test_retry_never_retries_refusal() -> None:
    inner = ScriptedGateway(FAKE_TEST_PROFILE, [ModelRefusalError("no")])
    gateway = RetryingGateway(inner, sleep=_ignore_sleep)
    with pytest.raises(ModelRefusalError):
        asyncio.run(gateway.complete(_request()))
    assert inner.calls == 1


def test_selection_defaults_to_fake() -> None:
    gateways, profiles = gateways_for_settings(Settings())
    assert set(gateways) == {"character", "reaction", "resolver", "narrator", "director", "summary"}
    assert all(isinstance(gateway, FakeGateway) for gateway in gateways.values())
    assert profiles["narrator"].adapter == "fake"


def test_selection_wires_openrouter_with_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORLDSIM_PROVIDER__ACTIVE_PROFILE", "openrouter")
    monkeypatch.setenv("WORLDSIM_PROVIDER__OPENROUTER_API_KEY", "sk-test-key")
    gateways, profiles = gateways_for_settings(Settings())
    narrator = gateways["narrator"]
    assert isinstance(narrator, RetryingGateway)
    assert narrator.profile.adapter == "openrouter"
    assert profiles["narrator"].adapter == "openrouter"


def test_selection_rejects_openrouter_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORLDSIM_PROVIDER__ACTIVE_PROFILE", "openrouter")
    monkeypatch.delenv("WORLDSIM_PROVIDER__OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="without credentials"):
        Settings()


def test_compute_cost_priced_model() -> None:
    cost = compute_cost(uuid4(), "openai/gpt-4o-mini", 1000, 1000, 4000)
    assert cost.pricing_version == PRICING_VERSION
    assert cost.estimated is False
    assert cost.prompt_cost_usd == pytest.approx(0.00015)
    assert cost.completion_cost_usd == pytest.approx(0.0006)


def test_compute_cost_unknown_model_is_estimated() -> None:
    cost = compute_cost(uuid4(), "some-future-model-9", 1000, 1000, 4000)
    assert cost.estimated is True
    assert cost.prompt_cost_usd > 0


def test_compute_cost_zero_tokens_byte_estimates() -> None:
    cost = compute_cost(uuid4(), "openai/gpt-4o-mini", 0, 0, 4000)
    assert cost.estimated is True
    assert cost.prompt_tokens == 1000
    assert cost.completion_tokens == 0


@pytest.fixture
def prov(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def _wait_json(actor: UUID) -> str:
    return json.dumps(
        {"family": "wait", "character_id": str(actor), "snapshot_id": PLACEHOLDER_SNAPSHOT}
    )


def test_every_call_gets_a_cost_row(prov: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = prov

    def _route(request: Any) -> str | None:
        prompt, system = request.prompt, request.system or ""
        if "You decide" in system:
            return _wait_json(WREN_ID if "Wren" in prompt else ASH_ID)
        if "You react" in system:
            return _wait_json(ASH_ID if "Ash" in prompt else WREN_ID)
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Quiet."})
        if "You narrate" in system:
            return json.dumps(
                [{"text": "The phase passes.", "cited_fact_keys": ["attempt:wait"]}]
            )
        if "You direct" in system:
            return json.dumps({"action": "noop", "reason": "calm stretch"})
        if "You summar" in system:
            return json.dumps({"text": "A quiet day.", "source_ids": []})
        if "You distill" in system:
            return json.dumps({"text": "Enduring.", "source_ids": []})
        return None

    gateway.route = _route
    headers = {"X-Worldsim-Role": "watcher"}
    client.post("/api/v1/world/seed", headers=headers)
    for index in range(1, 12):
        response = client.post(
            "/api/v1/stage1/advance",
            json={"world_id": str(WORLD_ID), "absolute_index": index},
            headers=headers,
        )
        assert response.status_code == 200, response.text

    async def _audit() -> tuple[int, int, float]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                calls = 0
                costs = 0
                for index in range(1, 12):
                    from worldsim.application.orchestration.service import derive_run_id

                    run = await uow.phases.get_run(derive_run_id(WORLD_ID, index))
                    for call in await uow.traces.list_for_phase_run(run.id):
                        calls += 1
                        assert await uow.costs.get_for_call(call.id) is not None
                        costs += 1
                return calls, costs, await uow.costs.total_for_world(WORLD_ID)
        finally:
            await engine.dispose()

    calls, costs, total = asyncio.run(_audit())
    assert calls > 0
    assert costs == calls
    assert total >= 0.0


def test_injected_factory_still_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORLDSIM_PROVIDER__ACTIVE_PROFILE", "fake")
    gateways, _ = gateways_for_settings(
        Settings(), fake_factory=lambda: FakeGateway(profile=FAKE_TEST_PROFILE)
    )
    assert all(isinstance(gateway, FakeGateway) for gateway in gateways.values())


def test_retrying_gateway_satisfies_port_shape() -> None:
    gateway = RetryingGateway(FakeGateway(profile=FAKE_TEST_PROFILE))
    assert gateway.profile.adapter == "fake"
    for method in ("complete", "embed", "probe"):
        assert callable(getattr(gateway, method))
