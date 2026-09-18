"""Revamp A04: duplicate presets and preset-scoped asset retrieval."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.domain.assets import AssetKind, AssetRecord
from worldsim.domain.ids import new_asset_id, new_world_id
from worldsim.domain.world import World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"


WREN_PRESET_ID = "20000000-0000-4000-8000-000000000101"


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


def _add_asset(world_id: UUID | None) -> UUID:
    async def _inner() -> UUID:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                asset_id = new_asset_id()
                await uow.assets.add_asset(
                    AssetRecord(
                        id=asset_id,
                        world_id=world_id,
                        kind=AssetKind.PORTRAIT,
                        subject_id=None,
                        content_ref="revamp/wren-portrait-v1.png",
                        mime="image/png",
                        width=256,
                        height=256,
                        style_pack_version="anime-saga-v1",
                    )
                )
                await uow.commit()
                return asset_id
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def _add_world() -> UUID:
    async def _inner() -> UUID:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Second", seed_version="a04"))
                await uow.commit()
                return wid
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def test_duplicate_copies_revision_and_stays_editable(client: ApiClient) -> None:
    made = client.post(
        "/api/v1/library/presets",
        json={"kind": "character", "name": "Miri", "payload": {"name": "Miri"}},
        headers={},
    )
    assert made.status_code == 200, made.text
    revised = client.post(
        f"/api/v1/library/presets/{made.json()['id']}/revisions",
        json={"payload": {"name": "Miri of the ford"}, "expected_version": 0},
        headers={},
    )
    assert revised.status_code == 200, revised.text
    dup = client.post(f"/api/v1/library/presets/{made.json()['id']}/duplicate", headers={})
    assert dup.status_code == 200, dup.text
    body = dup.json()
    assert body["name"] == "Miri copy"
    assert body["current_revision"] == 1
    assert body["revision"]["name"] == "Miri of the ford"
    assert body["builtin"] is False


def test_duplicate_builtin_leaves_original_readonly(client: ApiClient) -> None:
    dup = client.post(f"/api/v1/library/presets/{WREN_PRESET_ID}/duplicate", headers={})
    assert dup.status_code == 200, dup.text
    assert dup.json()["builtin"] is False
    original = client.get(f"/api/v1/library/presets/{WREN_PRESET_ID}", headers={})
    assert original.json()["readonly"] is True


def test_library_bytes_scope_and_archive_preserves_art(client: ApiClient) -> None:
    unscoped = _add_asset(None)
    wid = _add_world()
    bound = _add_asset(wid)

    served = client.get(f"/api/v1/library/assets/{unscoped}/bytes", headers={})
    assert served.status_code == 200, served.text
    assert served.headers["content-type"] == "image/png"

    refused = client.get(f"/api/v1/library/assets/{bound}/bytes", headers={})
    assert refused.status_code == 404, refused.text

    listed = client.get("/api/v1/library/assets", params={"kind": "portrait"}, headers={})
    assert listed.status_code == 200, listed.text
    assert {item["id"] for item in listed.json()} == {str(unscoped)}

    archived = client.post(
        f"/api/v1/library/presets/{WREN_PRESET_ID}/archive",
        json={"expected_version": 0},
        headers={},
    )
    assert archived.status_code == 200, archived.text
    still = client.get(f"/api/v1/library/assets/{unscoped}/bytes", headers={})
    assert still.status_code == 200, still.text


def test_invalid_import_writes_nothing(client: ApiClient) -> None:
    before = client.get("/api/v1/library/presets", headers={}).json()
    preview = client.post(
        "/api/v1/library/import/validate",
        json={"kind": "character", "name": "Bad", "payload": {"tags": "not-a-list"}},
        headers={},
    )
    assert preview.status_code == 422, preview.text
    applied = client.post(
        "/api/v1/library/import/apply",
        json={"kind": "character", "name": "Bad", "payload": {"tags": "not-a-list"}},
        headers={},
    )
    assert applied.status_code == 422, applied.text
    after = client.get("/api/v1/library/presets", headers={}).json()
    assert [item["id"] for item in after] == [item["id"] for item in before]
