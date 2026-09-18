"""Revamp A06: atomic creation, idempotent receipts, failure atomicity."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

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
WREN_PRESET_ID = "20000000-0000-4000-8000-000000000101"
ASH_PRESET_ID = "20000000-0000-4000-8000-000000000102"


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
        yield ApiClient(raw)


def _draft(client: ApiClient, role: str = "watcher", controlled: str | None = None) -> str:
    mode: dict[str, str] = {"role": role}
    if controlled:
        mode["controlled_cast_key"] = controlled
    created = client.post(
        "/api/v1/story-drafts",
        json={
            "payload": {
                "world": {"preset_id": WORLD_PRESET_ID, "preset_revision": 1},
                "cast": [
                    {
                        "instance_key": "cast-wren",
                        "preset_id": WREN_PRESET_ID,
                        "preset_revision": 1,
                        "name": "Wren",
                        "location_key": "hearth",
                    },
                    {
                        "instance_key": "cast-ash",
                        "preset_id": ASH_PRESET_ID,
                        "preset_revision": 1,
                        "name": "Ash",
                        "location_key": "market",
                    },
                ],
                "mode": mode,
                "story": {"title": "The Sealed Gate", "tone": "hopeful mystery"},
                "ai": {"art_source": "curated"},
            },
            "current_step": "review",
        },
        headers={},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _create(
    client: ApiClient, draft_id: str, key: str, version: int = 1
) -> httpx.Response:
    return client.post(
        "/api/v1/stories",
        json={"draft_id": draft_id, "expected_draft_version": version},
        headers={"Idempotency-Key": key},
    )


def _worlds(client: ApiClient) -> list[dict[str, object]]:
    return client.get("/api/v1/stories", headers={}).json()["items"]


def test_two_stories_from_one_template_are_independent(client: ApiClient) -> None:
    first = _create(client, _draft(client), "key-one")
    assert first.status_code == 200, first.text
    second = _create(client, _draft(client), "key-two")
    assert second.status_code == 200, second.text
    assert first.json()["world_id"] != second.json()["world_id"]

    for body in (first.json(), second.json()):
        detail = client.get(f"/api/v1/stories/{body['world_id']}", headers={})
        assert detail.status_code == 200, detail.text
        setup = client.get(f"/api/v1/stories/{body['world_id']}/setup", headers={})
        assert setup.status_code == 200, setup.text
        payload = setup.json()["payload"]
        assert payload["provenance"] == "created"
        cast_ids = [m["runtime_character_id"] for m in payload["cast"]]
        assert len(set(cast_ids)) == 2

    async def _ids() -> set[str]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                seen: set[str] = set()
                for body in (first.json(), second.json()):
                    for row in await uow.characters.list_for_world(UUID(body["world_id"])):
                        seen.add(str(row.id))
                return seen
        finally:
            await engine.dispose()

    assert len(asyncio.run(_ids())) == 4


def test_duplicate_submission_replays_one_story(client: ApiClient) -> None:
    draft_id = _draft(client)
    first = _create(client, draft_id, "same-key")
    assert first.status_code == 200, first.text
    assert first.json()["replayed"] is False
    again = _create(client, draft_id, "same-key")
    assert again.status_code == 200, again.text
    assert again.json()["replayed"] is True
    assert again.json()["world_id"] == first.json()["world_id"]
    assert len(_worlds(client)) == 1


def test_concurrent_duplicate_creates_one_story(client: ApiClient) -> None:
    draft_id = _draft(client)
    outcomes: list[httpx.Response] = []

    def _run() -> None:
        outcomes.append(_create(client, draft_id, "race-key"))

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(response.status_code == 200 for response in outcomes), [
        (r.status_code, r.text) for r in outcomes
    ]
    assert outcomes[0].json()["world_id"] == outcomes[1].json()["world_id"]
    assert len(_worlds(client)) == 1


def test_failed_create_leaves_no_partial_story(client: ApiClient) -> None:
    draft_id = _draft(client)
    before = len(_worlds(client))
    bad = client.post(
        "/api/v1/stories",
        json={"draft_id": draft_id, "expected_draft_version": 99},
        headers={"Idempotency-Key": "bad-version"},
    )
    assert bad.status_code == 409, bad.text
    assert len(_worlds(client)) == before
    draft = client.get(f"/api/v1/story-drafts/{draft_id}", headers={})
    assert draft.json()["version"] == 1
    assert draft.json()["created_world_id"] is None


def test_player_binds_chosen_actor(client: ApiClient) -> None:
    draft_id = _draft(client, role="player", controlled="cast-ash")
    created = _create(client, draft_id, "player-key")
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["role"] == "player"
    setup = client.get(f"/api/v1/stories/{body['world_id']}/setup", headers={}).json()
    assert setup["payload"]["mode"]["controlled_character_id"] == body["character_id"]
    ash = next(m for m in setup["payload"]["cast"] if m["instance_key"] == "cast-ash")
    assert ash["runtime_character_id"] == body["character_id"]
