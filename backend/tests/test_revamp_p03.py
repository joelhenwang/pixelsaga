"""Revamp P03: capability policy, identity linkage, presentation contracts."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"

WORLD = UUID("10000000-0000-4000-8000-000000000001")
WREN = UUID("10000000-0000-4000-8000-000000000101")
ASH = UUID("10000000-0000-4000-8000-000000000102")
HEARTH = UUID("10000000-0000-4000-8000-000000000011")
MARKET = UUID("10000000-0000-4000-8000-000000000012")


@pytest.fixture
def client(migrated_db: None) -> Iterator[ApiClient]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = lambda request: None  # noqa: E731
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


def _director() -> dict[str, str]:
    return {"X-Worldsim-Role": "director"}


def _deity() -> dict[str, str]:
    return {"X-Worldsim-Role": "deity"}


def _player(character: UUID) -> dict[str, str]:
    return {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(character)}


def _intents(actor: UUID) -> dict[str, object]:
    return {
        str(actor): {
            "family": "wait",
            "character_id": str(actor),
            "snapshot_id": "00000000-0000-4000-8000-000000000000",
        }
    }


def test_watcher_files_no_attempts(client: ApiClient) -> None:
    response = client.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(WORLD), "absolute_index": 1, "player_intents": _intents(WREN)},
        headers=_watcher(),
    )
    assert response.status_code == 403, response.text


def test_director_and_deity_use_queue_not_advance(client: ApiClient) -> None:
    for headers in (_director(), _deity()):
        response = client.post(
            "/api/v1/stage1/advance",
            json={
                "world_id": str(WORLD),
                "absolute_index": 1,
                "player_intents": _intents(WREN),
            },
            headers=headers,
        )
        assert response.status_code == 403, response.text


def test_player_substitutes_only_self(client: ApiClient) -> None:
    response = client.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(WORLD), "absolute_index": 1, "player_intents": _intents(ASH)},
        headers=_player(WREN),
    )
    assert response.status_code == 403, response.text


def test_operator_modes_read_world(client: ApiClient) -> None:
    for headers in (_director(), _deity()):
        characters = client.get(
            "/api/v1/stage1/characters", params={"world_id": str(WORLD)}, headers=headers
        )
        assert characters.status_code == 200, characters.text
        assert len(characters.json()) == 2
        world_map = client.get(
            "/api/v1/stage2/map", params={"world_id": str(WORLD)}, headers=headers
        )
        assert world_map.status_code == 200, world_map.text
        hearth = next(p for p in world_map.json()["places"] if p["id"] == str(HEARTH))
        assert hearth["occupant_ids"] == [str(WREN)]


def test_activity_writes_need_force_or_ownership(client: ApiClient) -> None:
    foreign = client.post(
        "/api/v1/stage2/activities",
        json={"world_id": str(WORLD), "character_id": str(ASH), "kind": "rest"},
        headers=_player(WREN),
    )
    assert foreign.status_code == 403, foreign.text

    directed = client.post(
        "/api/v1/stage2/activities",
        json={"world_id": str(WORLD), "character_id": str(ASH), "kind": "rest"},
        headers=_director(),
    )
    assert directed.status_code == 403, directed.text

    forced = client.post(
        "/api/v1/stage2/activities",
        json={"world_id": str(WORLD), "character_id": str(ASH), "kind": "rest"},
        headers=_deity(),
    )
    assert forced.status_code == 200, forced.text
    assert forced.json()["to_location_id"] is None
    assert forced.json()["effective_progress_phases"] is None


def test_create_and_seat_linked_character(client: ApiClient) -> None:
    created = client.post(
        "/api/v1/stage1/characters",
        json={"world_id": str(WORLD), "name": "Lyra", "location_id": str(HEARTH)},
        headers=_watcher(),
    )
    assert created.status_code == 200, created.text
    lyra = UUID(created.json()["id"])

    seated = client.post(
        "/api/v1/stage1/party/begin",
        json={"world_id": str(WORLD), "name": "Lyra", "character_id": str(lyra)},
        headers=_watcher(),
    )
    assert seated.status_code == 200, seated.text
    assert seated.json()["character_id"] == str(lyra)

    roster = client.get("/api/v1/stage1/party", params={"world_id": str(WORLD)}, headers=_watcher())
    assert roster.status_code == 200
    assert any(m["character_id"] == str(lyra) for m in roster.json()["members"])


def test_link_existing_member_with_version_check(client: ApiClient) -> None:
    seated = client.post(
        "/api/v1/stage1/party/begin",
        json={"world_id": str(WORLD), "name": "Bram"},
        headers=_watcher(),
    )
    assert seated.status_code == 200, seated.text
    member = seated.json()
    assert member["character_id"] is None

    linked = client.post(
        f"/api/v1/stage1/party/{member['id']}/link",
        json={"world_id": str(WORLD), "character_id": str(WREN), "expected_version": member["version"]},
        headers=_watcher(),
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["character_id"] == str(WREN)

    stale = client.post(
        f"/api/v1/stage1/party/{member['id']}/link",
        json={"world_id": str(WORLD), "character_id": str(WREN), "expected_version": member["version"]},
        headers=_watcher(),
    )
    assert stale.status_code == 409, stale.text

    taken = client.post(
        f"/api/v1/stage1/party/{member['id']}/link",
        json={
            "world_id": str(WORLD),
            "character_id": str(ASH),
            "expected_version": linked.json()["version"],
        },
        headers=_watcher(),
    )
    assert taken.status_code == 409, taken.text


def test_presentation_snapshot_shape(client: ApiClient) -> None:
    ensured = client.post(
        "/api/v1/assets/ensure-starter", json={"world_id": str(WORLD)}, headers=_watcher()
    )
    assert ensured.status_code == 200, ensured.text
    response = client.get(
        "/api/v1/world/presentation", params={"world_id": str(WORLD)}, headers=_watcher()
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["capabilities"]["role"] == "watcher"
    assert "advance" in body["capabilities"]["capabilities"]
    assert body["manifest"]["schematic"] is False
    assert body["manifest"]["asset_id"] is not None
    anchors = {a["location_id"]: (a["x"], a["y"]) for a in body["manifest"]["anchors"]}
    assert anchors[str(HEARTH)] == (0.22, 0.34)
    assert anchors[str(MARKET)] == (0.8, 0.44)
    cast = {c["character_id"]: c for c in body["cast"]}
    assert set(cast) == {str(WREN), str(ASH)}
    assert cast[str(WREN)]["portrait_asset_id"] is not None
    assert body["revision"] >= 0


def test_chronicle_cursor_advances(client: ApiClient) -> None:
    first = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(WORLD), "after": 0, "limit": 20},
        headers=_watcher(),
    )
    assert first.status_code == 200, first.text
    cursor = first.json()["next_after"]
    second = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(WORLD), "after": cursor, "limit": 20},
        headers=_watcher(),
    )
    assert second.status_code == 200, second.text
    assert second.json()["next_after"] >= cursor
    assert second.json()["has_more"] is False


def test_timeline_carries_cursor(client: ApiClient) -> None:
    response = client.get(
        "/api/v1/stage2/timeline",
        params={"world_id": str(WORLD), "after": 0, "limit": 20},
        headers=_watcher(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "next_after" in body and "has_more" in body
