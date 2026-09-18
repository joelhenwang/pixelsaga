"""Revamp P04: asset pipeline, fixture jobs, starter content."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.domain.assets import AssetKind, JobStatus
from worldsim.infrastructure.assets.fixture import FixtureImageGateway
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.storage.local import LocalStorage
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"

WORLD = UUID("10000000-0000-4000-8000-000000000001")
WREN = UUID("10000000-0000-4000-8000-000000000101")
ASH = UUID("10000000-0000-4000-8000-000000000102")


@pytest.fixture
def client(migrated_db: None) -> Iterator[ApiClient]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = lambda request: None
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        seeded = raw.post("/api/v1/world/seed")
        assert seeded.status_code == 200, seeded.text
        yield ApiClient(raw)


def _watcher() -> dict[str, str]:
    return {"X-Worldsim-Role": "watcher"}


def _player(character: UUID) -> dict[str, str]:
    return {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(character)}


def test_ensure_starter_registers_curated_set(client: ApiClient) -> None:
    first = client.post(
        "/api/v1/assets/ensure-starter", json={"world_id": str(WORLD)}, headers=_watcher()
    )
    assert first.status_code == 200, first.text
    assets = first.json()
    assert len(assets) == 5
    assert {a["style_pack_version"] for a in assets} == {"anime-saga-v1"}
    wren = [a for a in assets if a["subject_id"] == str(WREN)]
    assert len(wren) == 1 and wren[0]["kind"] == "portrait"

    second = client.post(
        "/api/v1/assets/ensure-starter", json={"world_id": str(WORLD)}, headers=_watcher()
    )
    assert second.status_code == 200, second.text
    assert [a["id"] for a in second.json()] == [a["id"] for a in assets]


def test_job_request_is_idempotent_and_completes(client: ApiClient) -> None:
    body = {
        "world_id": str(WORLD),
        "kind": "portrait",
        "subject_id": str(WREN),
        "idempotency_key": "p04-job-1",
    }
    first = client.post("/api/v1/assets/jobs", json=body, headers=_watcher())
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "pending"
    second = client.post("/api/v1/assets/jobs", json=body, headers=_watcher())
    assert second.json()["id"] == first.json()["id"]

    async def _complete() -> None:
        engine = create_engine(Settings())
        try:
            gateway = FixtureImageGateway(lambda: create_unit_of_work(engine))
            storage = LocalStorage(ROOT / "content" / "assets")
            asset = await gateway.complete(
                UUID(first.json()["id"]),
                storage,
                "revamp/wren-portrait-v1.png",
                "image/png",
                768,
                768,
            )
            assert asset.subject_visual_version == 1
            second_job = await gateway.request(
                WORLD, AssetKind.PORTRAIT, WREN, "anime-saga-v1", "p04-job-2"
            )
            again = await gateway.complete(
                second_job.id,
                storage,
                "revamp/ash-portrait-v1.png",
                "image/png",
                768,
                768,
            )
            assert again.id != asset.id
            assert again.subject_visual_version == 2
        finally:
            await engine.dispose()

    asyncio.run(_complete())

    job = client.get(f"/api/v1/assets/jobs/{first.json()['id']}", headers=_watcher())
    assert job.json()["status"] == "ready"
    assert job.json()["attempt_count"] == 0


def test_job_attempts_bound_then_fail(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            gateway = FixtureImageGateway(factory)
            job = await gateway.request(
                None, AssetKind.PORTRAIT, None, "anime-saga-v1", "p04-bound"
            )
            for _ in range(2):
                pending = await gateway.note_attempt(job.id, "boom")
                assert pending.status == JobStatus.PENDING
            failed = await gateway.note_attempt(job.id, "boom")
            assert failed.status == JobStatus.FAILED
            assert failed.attempt_count == 3
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_bytes_served_with_perspective(client: ApiClient) -> None:
    ensured = client.post(
        "/api/v1/assets/ensure-starter", json={"world_id": str(WORLD)}, headers=_watcher()
    )
    assets = {a["subject_id"]: a for a in ensured.json() if a["subject_id"]}
    wren_asset = assets[str(WREN)]
    ash_asset = assets[str(ASH)]
    world_map = next(a for a in ensured.json() if a["kind"] == "map")

    got = client.get(
        f"/api/v1/assets/{wren_asset['id']}",
        params={"world_id": str(WORLD)},
        headers=_player(WREN),
    )
    assert got.status_code == 200, got.text
    assert got.headers["content-type"] == "image/png"
    assert len(got.content) > 100_000

    foreign = client.get(
        f"/api/v1/assets/{ash_asset['id']}",
        params={"world_id": str(WORLD)},
        headers=_player(WREN),
    )
    assert foreign.status_code == 403, foreign.text

    public = client.get(
        f"/api/v1/assets/{world_map['id']}",
        params={"world_id": str(WORLD)},
        headers=_player(WREN),
    )
    assert public.status_code == 200, public.text
