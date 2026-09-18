"""Revamp A03: catalog backfill, drafts, preset revisions, built-in idempotence."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.application.library.builtins import (
    WREN_PRESET_ID,
    ensure_builtin_presets,
)
from worldsim.domain.ids import new_world_id
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

WORLD_PRESET_ID = "20000000-0000-4000-8000-000000000001"


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


def _config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    return config


def test_legacy_worlds_backfill_catalog_and_unknown_setup(
    migrated_db: None, client: ApiClient
) -> None:
    async def _make_world() -> UUID:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Legacy", seed_version="a03"))
                await uow.commit()
                return wid
        finally:
            await engine.dispose()

    alembic_command.downgrade(_config(), "0029_revamp_conditions")
    wid = asyncio.run(_make_world())
    alembic_command.upgrade(_config(), "head")

    catalog = client.get(f"/api/v1/stories/{wid}", headers={})
    assert catalog.status_code == 200, catalog.text
    assert catalog.json()["title"] == "Legacy"
    setup = client.get(f"/api/v1/stories/{wid}/setup", headers={})
    assert setup.status_code == 200, setup.text
    assert setup.json()["provenance"] == "legacy_unknown"


def test_builtin_presets_import_idempotent(client: ApiClient) -> None:
    async def _ensure() -> int:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                added = await ensure_builtin_presets(uow)
                await uow.commit()
                return added
        finally:
            await engine.dispose()

    assert asyncio.run(_ensure()) == 0
    listed = client.get("/api/v1/library/presets", headers={})
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 5
    assert asyncio.run(_ensure()) == 0
    again = client.get("/api/v1/library/presets", headers={})
    assert len(again.json()) == 5
    wren = client.get(f"/api/v1/library/presets/{WREN_PRESET_ID}", headers={})
    assert wren.status_code == 200, wren.text
    assert wren.json()["revision"]["name"] == "Wren"


def test_draft_version_conflict_and_consumed_guard(client: ApiClient) -> None:
    created = client.post(
        "/api/v1/story-drafts", json={"payload": {}, "current_step": "world"}, headers={}
    )
    assert created.status_code == 200, created.text
    draft_id = created.json()["id"]
    stale = client.patch(
        f"/api/v1/story-drafts/{draft_id}",
        json={
            "payload": {},
            "current_step": "characters",
            "expected_version": 99,
        },
        headers={},
    )
    assert stale.status_code == 409, stale.text
    saved = client.patch(
        f"/api/v1/story-drafts/{draft_id}",
        json={
            "payload": {"mode": {"role": "watcher"}},
            "current_step": "characters",
            "expected_version": 1,
        },
        headers={},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 2
    valid = client.post(f"/api/v1/story-drafts/{draft_id}/validate", headers={})
    assert valid.status_code == 200, valid.text
    assert valid.json()["valid"] is False  # empty cast
    deleted = client.delete(f"/api/v1/story-drafts/{draft_id}", headers={})
    assert deleted.status_code == 200, deleted.text


def test_preset_revision_immutable_and_builtin_readonly(client: ApiClient) -> None:
    made = client.post(
        "/api/v1/library/presets",
        json={
            "kind": "character",
            "name": "Miri",
            "payload": {"name": "Miri", "tags": ["Scout"]},
        },
        headers={},
    )
    assert made.status_code == 200, made.text
    preset_id = made.json()["id"]
    assert made.json()["current_revision"] == 1
    revised = client.post(
        f"/api/v1/library/presets/{preset_id}/revisions",
        json={"payload": {"name": "Miri", "tags": ["Scout", "Guide"]}, "expected_version": 0},
        headers={},
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["current_revision"] == 2
    first = client.get(f"/api/v1/library/presets/{preset_id}", params={"revision": 1}, headers={})
    assert first.status_code == 200, first.text
    assert first.json()["revision"]["tags"] == ["Scout"]
    builtin = client.post(
        f"/api/v1/library/presets/{WORLD_PRESET_ID}/revisions",
        json={"payload": {"name": "X"}, "expected_version": 0},
        headers={},
    )
    assert builtin.status_code == 403, builtin.text
    bad_kind = client.post(
        "/api/v1/library/presets",
        json={
            "kind": "character",
            "name": "Bad",
            "payload": {"name": "Bad", "starting_location_key": 5},
        },
        headers={},
    )
    assert bad_kind.status_code == 422, bad_kind.text


def test_catalog_lists_seeded_story(client: ApiClient) -> None:
    seeded = client.post("/api/v1/world/seed", headers={})
    assert seeded.status_code == 200, seeded.text
    listed = client.get("/api/v1/stories", headers={})
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) >= 1
