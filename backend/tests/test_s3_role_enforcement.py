"""Role enforcement probes (owned by S3-RULE-001 prerequisite).

Every mutating route resolves the grant-selected role before the
header: grants win, allowlists deny, and bound players act only as
themselves. Reads keep header perspective (documented boundary).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from test_stage1_api import (  # pyright: ignore[reportPrivateUsage]
    ApiClient,
    _route_for,
)

from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"

WORLD_ID = UUID("10000000-0000-4000-8000-000000000001")
WREN_ID = UUID("10000000-0000-4000-8000-000000000101")
ASH_ID = UUID("10000000-0000-4000-8000-000000000102")
HEARTH_ID = UUID("10000000-0000-4000-8000-000000000011")


@pytest.fixture
def roles(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def _seed(client: ApiClient) -> dict[str, str]:
    response = client.post("/api/v1/world/seed", headers={"X-Worldsim-Role": "watcher"})
    assert response.status_code == 200, response.text
    return {"X-Worldsim-Role": "watcher"}


def _select(
    client: ApiClient, headers: dict[str, str], role: str, character: UUID | None = None
) -> None:
    body: dict[str, object] = {"world_id": str(WORLD_ID), "role": role}
    if character is not None:
        body["character_id"] = str(character)
    response = client.post("/api/v1/stage2/roles/select", json=body, headers=headers)
    assert response.status_code == 200, response.text


def _claim(client: ApiClient, headers: dict[str, str], speaker: UUID) -> httpx.Response:
    return client.post(
        "/api/v1/stage2/claims",
        json={
            "world_id": str(WORLD_ID),
            "speaker_id": str(speaker),
            "proposition": "The mill is haunted",
            "audience_location_id": str(HEARTH_ID),
        },
        headers=headers,
    )


def test_director_header_cannot_voice_claim(roles: tuple[ApiClient, FakeGateway]) -> None:
    client, _gateway = roles
    _seed(client)
    response = _claim(client, {"X-Worldsim-Role": "director"}, WREN_ID)
    assert response.status_code == 403, response.text


def test_director_grant_beats_watcher_header(
    roles: tuple[ApiClient, FakeGateway],
) -> None:
    client, _gateway = roles
    headers = _seed(client)
    _select(client, headers, "director")
    response = _claim(client, headers, WREN_ID)
    assert response.status_code == 403, response.text


def test_player_bound_to_own_claims(roles: tuple[ApiClient, FakeGateway]) -> None:
    client, _gateway = roles
    headers = _seed(client)
    _select(client, headers, "player", WREN_ID)
    assert _claim(client, headers, WREN_ID).status_code == 200
    assert _claim(client, headers, ASH_ID).status_code == 403


def test_player_bound_to_own_evidence(roles: tuple[ApiClient, FakeGateway]) -> None:
    client, _gateway = roles
    headers = _seed(client)
    _select(client, headers, "player", WREN_ID)

    def _evidence(source: UUID) -> httpx.Response:
        return client.post(
            "/api/v1/stage2/relationships/evidence",
            json={
                "world_id": str(WORLD_ID),
                "source_id": str(source),
                "target_id": str(ASH_ID),
                "dimension": "trust",
                "delta": 1,
            },
            headers=headers,
        )

    assert _evidence(WREN_ID).status_code == 200
    assert _evidence(ASH_ID).status_code == 403


def test_items_and_activities_deny_director(
    roles: tuple[ApiClient, FakeGateway],
) -> None:
    client, _gateway = roles
    headers = _seed(client)
    director = {"X-Worldsim-Role": "director"}
    assert (
        client.post(
            "/api/v1/stage2/items/give",
            json={"world_id": str(WORLD_ID), "item_key": "rope", "quantity": 1},
            headers=director,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/stage2/activities",
            json={"world_id": str(WORLD_ID), "character_id": str(WREN_ID), "kind": "rest"},
            headers=director,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/stage2/activities",
            json={"world_id": str(WORLD_ID), "character_id": str(WREN_ID), "kind": "rest"},
            headers=headers,
        ).status_code
        == 200
    )


def test_watcher_grant_wins_over_bare_player_header(
    roles: tuple[ApiClient, FakeGateway],
) -> None:
    client, _gateway = roles
    headers = _seed(client)
    bare_player = {"X-Worldsim-Role": "player"}
    assert _claim(client, bare_player, WREN_ID).status_code == 403
    _select(client, headers, "watcher")
    assert _claim(client, bare_player, WREN_ID).status_code == 200


def test_advance_allows_director_without_intents(roles: tuple[ApiClient, FakeGateway]) -> None:
    """Directors hold ADVANCE: plain advance is authorized (A02 fixed the
    blanket watcher/player gate that used to 403 here)."""
    client, gateway = roles
    _seed(client)
    ids = {"world": WORLD_ID, "wren": WREN_ID, "ash": ASH_ID}
    snapshots = {1: derive_snapshot_id(derive_run_id(WORLD_ID, 1))}
    gateway.route = _route_for(ids, snapshots)
    response = client.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(WORLD_ID), "absolute_index": 1},
        headers={"X-Worldsim-Role": "director"},
    )
    assert response.status_code == 200, response.text
