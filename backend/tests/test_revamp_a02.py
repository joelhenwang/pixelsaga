"""Revamp A02: explicit world selection and Director/Deity capability policy."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import (
    ApiClient,
    FakeGateway,
    _advance,  # pyright: ignore[reportPrivateUsage]
    _route_for,  # pyright: ignore[reportPrivateUsage]
    _seed_two,  # pyright: ignore[reportPrivateUsage]
)

from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
from worldsim.domain.phases import PhaseRun
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"


@pytest.fixture
def story_api(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def _director() -> dict[str, str]:
    return {"X-Worldsim-Role": "director"}


def _deity() -> dict[str, str]:
    return {"X-Worldsim-Role": "deity"}


def _watcher() -> dict[str, str]:
    return {"X-Worldsim-Role": "watcher"}


def _add_second_world() -> UUID:
    async def _inner() -> UUID:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                ids = await _seed_two_inner(uow)
                await uow.commit()
                return ids
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


async def _seed_two_inner(uow: object) -> UUID:
    from worldsim.domain.ids import new_world_id
    from worldsim.domain.world import World

    wid = new_world_id()
    await uow.worlds.add(World(id=wid, name="Second", seed_version="a02-test"))  # type: ignore[attr-defined]
    return wid


def test_single_world_shortcut_still_works(
    story_api: tuple[ApiClient, FakeGateway],
) -> None:
    client, _ = story_api
    ids = asyncio.run(_seed_two())
    for path in ("/api/v1/world", "/api/v1/world/clock", "/api/v1/world/phases/current"):
        response = client.get(path, headers=_watcher())
        assert response.status_code == 200, (path, response.text)
    events = client.get("/api/v1/world/events", headers=_watcher())
    assert events.status_code == 200, events.text
    assert client.get("/api/v1/world", headers=_watcher()).json()["id"] == str(ids["world"])


def test_two_worlds_require_explicit_selection(
    story_api: tuple[ApiClient, FakeGateway],
) -> None:
    client, _ = story_api
    first = asyncio.run(_seed_two())
    second = _add_second_world()
    for path in (
        "/api/v1/world",
        "/api/v1/world/clock",
        "/api/v1/world/phases/current",
        "/api/v1/world/events",
    ):
        response = client.get(path, headers=_watcher())
        assert response.status_code == 409, (path, response.text)
        assert response.json()["error"]["details"]["code"] == "WORLD_SELECTION_REQUIRED"
    for wid in (first["world"], second):
        response = client.get(
            "/api/v1/world/clock", params={"world_id": str(wid)}, headers=_watcher()
        )
        assert response.status_code == 200, (wid, response.text)
    missing = client.get(
        "/api/v1/world",
        params={"world_id": "00000000-0000-4000-8000-000000000000"},
        headers=_watcher(),
    )
    assert missing.status_code == 404, missing.text


def test_director_and_deity_plain_advance(
    story_api: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = story_api
    ids = asyncio.run(_seed_two())
    snapshots = {
        1: derive_snapshot_id(derive_run_id(ids["world"], 1)),
        2: derive_snapshot_id(derive_run_id(ids["world"], 2)),
    }
    gateway.route = _route_for(ids, snapshots)  # type: ignore[attr-defined]
    first = _advance(client, ids["world"], 1, headers=_director())
    assert first.status_code == 200, first.text
    second = _advance(client, ids["world"], 2, headers=_deity())
    assert second.status_code == 200, second.text


def test_advances_on_two_worlds_stay_isolated(
    story_api: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = story_api
    first = asyncio.run(_seed_two())
    second_id = _add_second_world()
    snapshots = {
        1: derive_snapshot_id(derive_run_id(first["world"], 1)),
        2: derive_snapshot_id(derive_run_id(first["world"], 2)),
    }
    gateway.route = _route_for(first, snapshots)  # type: ignore[attr-defined]
    for index in (1, 2):
        response = _advance(client, first["world"], index, headers=_watcher())
        assert response.status_code == 200, (index, response.text)
    for wid in (first["world"], second_id):
        clock = client.get("/api/v1/world/clock", params={"world_id": str(wid)}, headers=_watcher())
        assert clock.status_code == 200, (wid, clock.text)
        expected = 2 if wid == first["world"] else 0
        assert clock.json()["absolute_index"] == expected, wid


def test_director_status_pause_resume(
    story_api: tuple[ApiClient, FakeGateway],
) -> None:
    client, _ = story_api
    ids = asyncio.run(_seed_two())
    run_id = derive_run_id(ids["world"], 1)

    async def _create() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await uow.phases.create_run(
                    PhaseRun(id=run_id, world_id=ids["world"], absolute_index=1)
                )
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(_create())
    status = client.get(
        "/api/v1/simulation/status",
        params={"world_id": str(ids["world"])},
        headers=_director(),
    )
    assert status.status_code == 200, status.text
    assert status.json()["world_id"] == str(ids["world"])
    paused = client.post("/api/v1/stage1/pause", json={"run_id": str(run_id)}, headers=_director())
    assert paused.status_code == 200, paused.text
    resumed = client.post("/api/v1/stage1/resume", json={"run_id": str(run_id)}, headers=_deity())
    assert resumed.status_code == 200, resumed.text
