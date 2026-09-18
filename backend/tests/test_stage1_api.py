"""Stage 1 API perspective and command checks (owned by S1-API-001)."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.ids import new_card_id, new_character_id, new_location_id, new_world_id
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"


class ApiClient:
    def __init__(self, raw: TestClient) -> None:
        self._raw = raw

    def _raw_any(self) -> Any:
        return self._raw

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return cast(httpx.Response, self._raw_any().get(url, **kwargs))

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return cast(httpx.Response, self._raw_any().post(url, **kwargs))


@pytest.fixture
def api(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway, dict[str, UUID]]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway, {}


async def _seed_two() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            await uow.worlds.add(World(id=wid, name="Api", seed_version="s1-test"))
            hearth, market = new_location_id(), new_location_id()
            await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth"))
            await uow.locations.add(Location(id=market, world_id=wid, name="Market"))
            wren, ash = new_character_id(), new_character_id()
            for cid, name, place in ((wren, "Wren", hearth), (ash, "Ash", market)):
                await uow.characters.add_identity(cid, wid, name)
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=cid, name=name, version=1)
                )
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=wid,
                        name=name,
                        card_version=1,
                        location_id=place,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
            await uow.versions.ensure(wid, wid, "world")
            await uow.commit()
            return {"world": wid, "wren": wren, "ash": ash}
    finally:
        await engine.dispose()


def _route_for(ids: dict[str, UUID], snapshots: dict[int, UUID]):
    def _route(request: CompletionRequest) -> str | None:
        prompt, system = request.prompt, request.system or ""
        if "You narrate" in system:
            return json.dumps([{"text": "The phase passes.", "cited_fact_keys": ["attempt:wait"]}])
        if "You resolve" in system:
            return json.dumps(
                {
                    "outcome": "success",
                    "effects": [
                        {
                            "schema_version": 1,
                            "affected_ids": [str(ids["wren"])],
                            "expected_versions": {str(ids["wren"]): 0},
                            "effect_type": "record_observation",
                            "observer_character_id": str(ids["wren"]),
                            "facts": [{"key": "greeting", "value": "dawn patrol"}],
                        }
                    ],
                    "rationale": "Wren hears the call.",
                }
            )
        snapshot = snapshots.get(1, next(iter(snapshots.values())) if snapshots else uuid.uuid4())
        if "You react" in system:
            if "Wren" in prompt:
                return json.dumps(
                    {
                        "family": "observe",
                        "character_id": str(ids["wren"]),
                        "snapshot_id": str(snapshot),
                        "focus": "Ash",
                    }
                )
            return json.dumps(
                {"family": "wait", "character_id": str(ids["ash"]), "snapshot_id": str(snapshot)}
            )
        if "You decide" in system:
            if "Wren" in prompt:
                return json.dumps(
                    {
                        "family": "wait",
                        "character_id": str(ids["wren"]),
                        "snapshot_id": str(snapshot),
                    }
                )
            if "Ash" in prompt:
                return json.dumps(
                    {
                        "family": "wait",
                        "character_id": str(ids["ash"]),
                        "snapshot_id": str(snapshot),
                    }
                )
        return None

    return _route


def _watcher() -> dict[str, str]:
    return {"X-Worldsim-Role": "watcher"}


def _player(character: UUID) -> dict[str, str]:
    return {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(character)}


def _advance(
    client: ApiClient,
    world: UUID,
    index: int,
    player_intents: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {"world_id": str(world), "absolute_index": index}
    if player_intents:
        body["player_intents"] = player_intents
    return client.post("/api/v1/stage1/advance", json=body, headers=headers or _watcher())


def test_watcher_and_player_views_differ(
    api: tuple[ApiClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, gateway, _ = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)
    report = _advance(client, ids["world"], 1)
    assert report.status_code == 200, report.text
    assert report.json()["duplicate"] is False

    run_id = report.json()["run_id"]
    watcher_scenes = client.get(
        "/api/v1/stage1/scenes", params={"phase_run_id": run_id}, headers=_watcher()
    )
    assert watcher_scenes.status_code == 200
    assert len(watcher_scenes.json()) == 2

    wren_scenes = client.get(
        "/api/v1/stage1/scenes", params={"phase_run_id": run_id}, headers=_player(ids["wren"])
    )
    assert wren_scenes.status_code == 200
    assert len(wren_scenes.json()) == 1

    ash_scene_id = next(
        s["id"] for s in watcher_scenes.json() if s["id"] != wren_scenes.json()[0]["id"]
    )
    forbidden = client.get(f"/api/v1/stage1/scenes/{ash_scene_id}", headers=_player(ids["wren"]))
    assert forbidden.status_code == 403


def test_player_intent_detail_scoped(api: tuple[ApiClient, FakeGateway, dict[str, UUID]]) -> None:
    client, gateway, _ = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)
    snapshot = snapshots[1]
    player = {
        str(ids["ash"]): {
            "family": "communicate",
            "character_id": str(ids["ash"]),
            "snapshot_id": str(snapshot),
            "target_character_id": str(ids["wren"]),
            "topic": "dawn patrol",
        }
    }
    report = _advance(client, ids["world"], 1, player, _player(ids["ash"]))
    assert report.status_code == 200, report.text
    scene_id = report.json()["scenes"][0]["scene_id"]

    wren_view = client.get(f"/api/v1/stage1/scenes/{scene_id}", headers=_player(ids["wren"]))
    assert wren_view.status_code == 200
    intents = {i["author_character_id"]: i for i in wren_view.json()["intents"]}
    assert intents[str(ids["wren"])]["detail"] is not None
    assert intents[str(ids["ash"])]["detail"] is None

    watcher_view = client.get(f"/api/v1/stage1/scenes/{scene_id}", headers=_watcher())
    watcher_intents = {i["author_character_id"]: i for i in watcher_view.json()["intents"]}
    assert watcher_intents[str(ids["ash"])]["detail"]["topic"] == "dawn patrol"


def test_model_runs_watcher_only(api: tuple[ApiClient, FakeGateway, dict[str, UUID]]) -> None:
    client, gateway, _ = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)
    report = _advance(client, ids["world"], 1)
    run_id = report.json()["run_id"]

    forbidden = client.get(
        "/api/v1/stage1/model-runs", params={"phase_run_id": run_id}, headers=_player(ids["wren"])
    )
    assert forbidden.status_code == 403

    allowed = client.get(
        "/api/v1/stage1/model-runs", params={"phase_run_id": run_id}, headers=_watcher()
    )
    assert allowed.status_code == 200
    assert len(allowed.json()) >= 2
    assert all("rendered_hash" in call for call in allowed.json())


def test_character_card_scoped(api: tuple[ApiClient, FakeGateway, dict[str, UUID]]) -> None:
    client, _gateway, _ = api
    ids = asyncio.run(_seed_two())

    watcher = client.get(f"/api/v1/stage1/characters/{ids['wren']}", headers=_watcher())
    assert watcher.json()["card"] is not None

    other = client.get(f"/api/v1/stage1/characters/{ids['ash']}", headers=_player(ids["wren"]))
    assert other.json()["card"] is None
    assert other.json()["name"] == "Ash"

    own = client.get(f"/api/v1/stage1/characters/{ids['wren']}", headers=_player(ids["wren"]))
    assert own.json()["card"] is not None


def test_duplicate_and_stale_advance_stable(
    api: tuple[ApiClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, gateway, _ = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)
    first = _advance(client, ids["world"], 1)
    second = _advance(client, ids["world"], 1)
    assert second.json()["duplicate"] is True
    assert [s["event_id"] for s in second.json()["scenes"]] == [
        s["event_id"] for s in first.json()["scenes"]
    ]

    gap = _advance(client, ids["world"], 5)
    assert gap.status_code == 422
    gap_again = _advance(client, ids["world"], 5)
    assert gap_again.status_code == 422
    assert gap_again.json()["error"]["code"] == gap.json()["error"]["code"]


def test_pause_resume_commands(api: tuple[ApiClient, FakeGateway, dict[str, UUID]]) -> None:
    client, gateway, _ = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)
    run_id = str(derive_run_id(ids["world"], 1))
    engine = create_engine(Settings())
    try:
        from worldsim.domain.phases import PhaseRun

        async def _create() -> None:
            async with create_unit_of_work(engine) as uow:
                await uow.phases.create_run(
                    PhaseRun(id=UUID(run_id), world_id=ids["world"], absolute_index=1)
                )
                await uow.commit()

        asyncio.run(_create())
    finally:
        asyncio.run(engine.dispose())
    paused = client.post("/api/v1/stage1/pause", json={"run_id": run_id}, headers=_watcher())
    assert paused.status_code == 200
    blocked = _advance(client, ids["world"], 1)
    assert blocked.status_code == 409
    resumed = client.post("/api/v1/stage1/resume", json={"run_id": run_id}, headers=_watcher())
    assert resumed.status_code == 200
    report = _advance(client, ids["world"], 1)
    assert report.status_code == 200


def test_event_cursor_reconnects(api: tuple[ApiClient, FakeGateway, dict[str, UUID]]) -> None:
    client, gateway, _ = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)
    _advance(client, ids["world"], 1)
    first = client.get("/api/v1/world/events", params={"after": 0, "limit": 1}, headers=_watcher())
    assert first.status_code == 200
    cursor = first.json()["next_after"]
    second = client.get(
        "/api/v1/world/events", params={"after": cursor, "limit": 50}, headers=_watcher()
    )
    full = client.get("/api/v1/world/events", params={"after": 0, "limit": 50}, headers=_watcher())
    assert [e["sequence"] for e in second.json()["entries"]] == [
        e["sequence"] for e in full.json()["entries"] if e["sequence"] > cursor
    ]


def test_ts_client_current() -> None:
    result = subprocess.run(
        [sys.executable, "backend/scripts/gen_ts_client.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
