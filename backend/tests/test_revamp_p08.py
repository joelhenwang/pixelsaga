"""Revamp P08: suggestions, player attempts, linked creation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from test_stage1_api import _route_for as _base_route_for  # pyright: ignore[reportPrivateUsage]
from test_stage1_api import _seed_two  # pyright: ignore[reportPrivateUsage]
from test_stage1_api import ApiClient

from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"


def _watcher() -> dict[str, str]:
    return {"X-Worldsim-Role": "watcher"}


def _player(character: UUID) -> dict[str, str]:
    return {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(character)}


@pytest.fixture
def client(migrated_db: None) -> Any:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = lambda request: None
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    from fastapi.testclient import TestClient

    with TestClient(app) as raw:
        seeded = raw.post("/api/v1/world/seed")
        assert seeded.status_code == 200, seeded.text
        yield ApiClient(raw)


WORLD = UUID("10000000-0000-4000-8000-000000000001")
WREN = UUID("10000000-0000-4000-8000-000000000101")
ASH = UUID("10000000-0000-4000-8000-000000000102")
HEARTH = UUID("10000000-0000-4000-8000-000000000011")


def test_suggestions_come_from_rules(client: ApiClient) -> None:
    response = client.get(
        "/api/v1/stage1/suggestions", params={"character_id": str(WREN)}, headers=_player(WREN)
    )
    assert response.status_code == 200, response.text
    families = {s["family"] for s in response.json()}
    assert {"rest", "observe", "appeal"} <= families
    assert "communicate" not in families
    assert "spar" not in families

    foreign = client.get(
        "/api/v1/stage1/suggestions", params={"character_id": str(ASH)}, headers=_player(WREN)
    )
    assert foreign.status_code == 403, foreign.text


def test_player_attempt_flows_through_queue(migrated_db: None) -> None:
    ids = asyncio.run(_seed_two())
    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    base = _base_route_for(ids, snapshots)

    def route(request: Any) -> Any:
        if "game-master" in (request.system or ""):
            return json.dumps(
                {
                    "schema_version": 1,
                    "steps": [
                        {
                            "kind": "direct_attempt",
                            "explanation": "Ash waits",
                            "character_id": str(ids["ash"]),
                            "family": "wait",
                            "action": {
                                "family": "wait",
                                "character_id": str(ids["ash"]),
                                "snapshot_id": "00000000-0000-4000-8000-000000000000",
                            },
                        }
                    ],
                    "clarification": "",
                }
            )
        return base(request)

    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = route

    async def _inner() -> None:
        app = create_app(
            Settings(),
            seed_dir=SEED_DIR,
            migrations_dir=MIGRATIONS,
            gateway_factory=lambda: gateway,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://p08") as http:
            player = {
                "X-Worldsim-Role": "player",
                "X-Worldsim-Character": str(ids["ash"]),
            }
            queued = await http.post(
                "/api/v1/interventions",
                json={
                    "world_id": str(ids["world"]),
                    "client_request_id": "p08-attempt-1",
                    "text": "Ash waits",
                    "mode": "attempt",
                    "scope": {"kind": "characters", "character_ids": [str(ids["ash"])]},
                    "effective_at": "next_boundary",
                },
                headers=player,
            )
            assert queued.status_code == 200, queued.text
            assert queued.json()["status"] == "queued"

            foreign = await http.post(
                "/api/v1/interventions",
                json={
                    "world_id": str(ids["world"]),
                    "client_request_id": "p08-attempt-2",
                    "text": "Wren waits",
                    "mode": "attempt",
                    "scope": {"kind": "characters", "character_ids": [str(ids["wren"])]},
                    "effective_at": "next_boundary",
                },
                headers=player,
            )
            assert foreign.status_code == 403, foreign.text

            advance = await http.post(
                "/api/v1/stage1/advance",
                json={"world_id": str(ids["world"]), "absolute_index": 1},
                headers=player,
            )
            assert advance.status_code == 200, advance.text
            done = await http.get(
                f"/api/v1/interventions/{queued.json()['id']}", headers=player
            )
            assert done.json()["status"] == "completed", done.text

    asyncio.run(_inner())


def test_create_link_select_flow(client: ApiClient) -> None:
    created = client.post(
        "/api/v1/stage1/characters",
        json={
            "world_id": str(WORLD),
            "name": "Lyra",
            "location_id": str(HEARTH),
            "appearance": "Copper pixie cut",
            "personality": "Bright and blunt",
        },
        headers=_watcher(),
    )
    assert created.status_code == 200, created.text
    lyra = created.json()["id"]

    seated = client.post(
        "/api/v1/stage1/party/begin",
        json={"world_id": str(WORLD), "name": "Lyra", "character_id": lyra},
        headers=_watcher(),
    )
    assert seated.json()["character_id"] == lyra, seated.text

    grant = client.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(WORLD), "role": "player", "character_id": lyra},
        headers=_watcher(),
    )
    assert grant.status_code == 200, grant.text
    assert grant.json()["character_id"] == lyra

    read = client.get("/api/v1/stage2/roles", params={"world_id": str(WORLD)}, headers=_watcher())
    assert read.json()["role"] == "player"
