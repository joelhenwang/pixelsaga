"""Revamp A05: provider revisions, sampling transmission, endpoint policy."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_stage1_api import ApiClient

from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.application.settings.endpoints import EndpointPolicy, validate_endpoint
from worldsim.application.settings.resolution import SamplingParams, resolve_sampling
from worldsim.domain.errors import DomainError
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.openrouter import OpenRouterGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"


@pytest.fixture
def client(migrated_db: None) -> Iterator[ApiClient]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw)


def test_sampling_flows_from_request_to_adapter_body() -> None:
    request = CompletionRequest(prompt="hello", max_tokens=64, temperature=0.7, top_p=0.9, top_k=40)
    gateway = OpenRouterGateway(
        FAKE_TEST_PROFILE,
        api_key=SecretStr("test-key"),
        base_url="https://example.test/v1",
    )
    body = gateway._body(request)  # pyright: ignore[reportPrivateUsage]
    assert body["temperature"] == 0.7
    assert body["top_p"] == 0.9
    assert body["top_k"] == 40
    assert body["model"] == "fake-echo"
    plain = CompletionRequest(prompt="hello")
    bare = gateway._body(plain)  # pyright: ignore[reportPrivateUsage]
    assert "temperature" not in bare and "top_p" not in bare and "top_k" not in bare


def test_fake_gateway_records_sampling_for_capture() -> None:
    async def _inner() -> None:
        gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
        gateway.route = lambda request: json.dumps({"ok": True})
        await gateway.complete(CompletionRequest(prompt="ping", temperature=0.5, top_k=10))
        sent = gateway.sent_requests[-1]
        assert sent.temperature == 0.5
        assert sent.top_k == 10
        assert sent.top_p is None

    asyncio.run(_inner())


def test_profile_revision_validation_and_secrets(client: ApiClient) -> None:
    made = client.post(
        "/api/v1/settings/providers",
        json={
            "adapter": "openrouter",
            "name": "Remote",
            "endpoint": "http://127.0.0.1:7143/v1",
            "credential_env": "WORLDSIM_TEST_KEY_ABSENT",
            "allow_local_endpoint": True,
        },
        headers={},
    )
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["has_credential"] is False
    connection_id = body["id"]

    os.environ["WORLDSIM_TEST_KEY_ABSENT"] = "secret-value"
    try:
        reread = client.get(f"/api/v1/settings/providers/{connection_id}", headers={})
        assert reread.json()["has_credential"] is True
        assert "secret-value" not in reread.text
    finally:
        del os.environ["WORLDSIM_TEST_KEY_ABSENT"]

    profile = client.post(
        f"/api/v1/settings/providers/{connection_id}/profiles",
        json={"model_id": "openrouter/auto", "temperature": 0.8, "top_k": 50},
        headers={},
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["temperature"] == 0.8

    bad = client.post(
        f"/api/v1/settings/providers/{connection_id}/profiles",
        json={"model_id": "x", "mystery_param": 1.0},
        headers={},
    )
    assert bad.status_code == 422, bad.text
    out_of_range = client.post(
        f"/api/v1/settings/providers/{connection_id}/profiles",
        json={"model_id": "x", "temperature": 9.0},
        headers={},
    )
    assert out_of_range.status_code == 422, out_of_range.text


def test_endpoint_policy_blocks_dangerous_targets() -> None:
    blocked = [
        "http://169.254.169.254/latest",
        "https://user:pass@example.com/v1",
        "https://example.com/v1?api_key=secret",
        "ftp://example.com/v1",
    ]
    for raw in blocked:
        try:
            validate_endpoint(raw, EndpointPolicy())
        except DomainError:
            continue
        raise AssertionError(f"endpoint accepted: {raw}")
    plain = "http://example.com/v1"
    try:
        validate_endpoint(plain, EndpointPolicy())
    except DomainError:
        pass
    else:
        raise AssertionError("plain http accepted without local allowance")
    loopback = validate_endpoint("http://127.0.0.1:11434/v1", EndpointPolicy(allow_local=True))
    assert loopback == "http://127.0.0.1:11434/v1"


def test_pinned_profile_resolves_per_world(client: ApiClient) -> None:
    connection = client.post(
        "/api/v1/settings/providers",
        json={
            "adapter": "fake",
            "name": "Demo",
            "endpoint": "http://127.0.0.1:7144/v1",
            "allow_local_endpoint": True,
        },
        headers={},
    ).json()
    profile = client.post(
        f"/api/v1/settings/providers/{connection['id']}/profiles",
        json={"model_id": "fake-echo", "temperature": 0.3},
        headers={},
    ).json()

    async def _setup() -> UUID:
        from test_stage1_api import _seed_two  # pyright: ignore[reportPrivateUsage]

        from worldsim.domain.stories import SetupProvenance, StoryInitialSetup
        from worldsim.domain.time import utcnow

        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                ids = await _seed_two()
                await uow.stories.put_setup(
                    StoryInitialSetup(
                        world_id=ids["world"],
                        payload={
                            "schema_version": 1,
                            "provenance": "created",
                            "ai": {
                                "profile_id": profile["id"],
                                "profile_revision": profile["revision"],
                            },
                        },
                        content_hash="a05-test",
                        created_at=utcnow(),
                        provenance=SetupProvenance.CREATED,
                    )
                )
                await uow.commit()
                return ids["world"]
        finally:
            await engine.dispose()

    world_id = asyncio.run(_setup())

    async def _resolve() -> SamplingParams:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                return await resolve_sampling(uow, world_id)
        finally:
            await engine.dispose()

    sampling = asyncio.run(_resolve())
    assert sampling.temperature == 0.3
    assert sampling.profile_id == profile["id"]


def test_preferences_versioned_and_probe_redacted(client: ApiClient) -> None:
    current = client.get("/api/v1/settings/preferences", headers={})
    assert current.status_code == 200, current.text
    assert current.json()["version"] == 0
    stale = client.patch(
        "/api/v1/settings/preferences",
        json={"gameplay": {"pacing": "brisk"}, "expected_version": 9},
        headers={},
    )
    assert stale.status_code == 409, stale.text
    saved = client.patch(
        "/api/v1/settings/preferences",
        json={
            "gameplay": {"pacing": "brisk", "autoplay_dwell": "fast"},
            "accessibility": {"font_scale": 112, "motion": "reduce"},
            "expected_version": 0,
        },
        headers={},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["version"] == 1
    assert body["gameplay"]["pacing"] == "brisk"
    bad = client.patch(
        "/api/v1/settings/preferences",
        json={"accessibility": {"font_scale": 500}, "expected_version": 1},
        headers={},
    )
    assert bad.status_code == 422, bad.text


def test_probe_shape_and_cache_scopes(client: ApiClient) -> None:
    made = client.post(
        "/api/v1/settings/providers",
        json={
            "adapter": "fake",
            "name": "Demo",
            "endpoint": "http://127.0.0.1:7145/v1",
            "allow_local_endpoint": True,
        },
        headers={},
    )
    assert made.status_code == 200, made.text
    probe = client.post(f"/api/v1/settings/providers/{made.json()['id']}/test", json={}, headers={})
    assert probe.status_code == 200, probe.text
    assert probe.json()["text_ready"] == "demo (scripted), never live"
    assert "tested_config_revision" in probe.json()

    caches = client.get("/api/v1/settings/cache", headers={})
    assert caches.status_code == 200, caches.text
    assert caches.json()[0]["scope"] == "image_derived"
    unknown = client.post("/api/v1/settings/cache/clear", json={"scope": "world_rows"}, headers={})
    assert unknown.status_code == 422, unknown.text
    cleared = client.post(
        "/api/v1/settings/cache/clear", json={"scope": "image_derived"}, headers={}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["removed"] >= 0
