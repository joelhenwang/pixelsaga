"""S0-API-001: HTTP boundary contracts (owned by S0-API-001)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient

from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"
OPENAPI = ROOT / "content" / "schemas" / "openapi.json"


class BoundaryClient:
    """Strict-typed facade over the untyped starlette test client."""

    def __init__(self, raw: TestClient) -> None:
        self._raw = raw

    def _raw_any(self) -> Any:
        return self._raw

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return cast(httpx.Response, self._raw_any().get(url, **kwargs))

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return cast(httpx.Response, self._raw_any().post(url, **kwargs))


@pytest.fixture
def boundary(migrated_db: None) -> Iterator[tuple[BoundaryClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield BoundaryClient(raw), gateway


def test_live_echoes_request_id(boundary: tuple[BoundaryClient, FakeGateway]) -> None:
    client, _gateway = boundary
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "req-demo-1"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "req-demo-1"


def test_ready_reports_versions_without_secrets(
    boundary: tuple[BoundaryClient, FakeGateway], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORLDSIM_SECURITY__API_KEY", "sentinel-key-xyz")
    client, _gateway = boundary
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["version"] == "0.1.0"
    assert body["migration_head"] == "0003_trace_correlation"
    assert body["schema_version"] == 1
    by_name = {check["name"]: check for check in body["checks"]}
    assert by_name["database"]["status"] == "ok"
    assert by_name["migrations"]["status"] == "ok"
    assert by_name["extensions"]["status"] == "ok"
    assert by_name["seed"]["status"] == "degraded"
    assert "sentinel-key-xyz" not in response.text


def test_world_missing_before_seed(boundary: tuple[BoundaryClient, FakeGateway]) -> None:
    client, _gateway = boundary
    response = client.get("/api/v1/world")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_seed_inspect_flow(boundary: tuple[BoundaryClient, FakeGateway]) -> None:
    client, _gateway = boundary
    first = client.post("/api/v1/world/seed")
    assert first.status_code == 200
    assert first.json()["seed_version"] == "stage0-v1"
    assert first.json()["duplicate"] is False
    world_id = first.json()["world_id"]
    second = client.post("/api/v1/world/seed")
    assert second.json()["duplicate"] is True
    assert second.json()["world_id"] == world_id

    world = client.get("/api/v1/world").json()
    assert world["id"] == world_id
    assert world["name"] == "Ember Vale"
    assert world["day"] == 1
    assert world["phase"] == "dawn"
    assert world["absolute_index"] == 0

    clock = client.get("/api/v1/world/clock").json()
    assert clock == {"day": 1, "phase": "dawn", "absolute_index": 0}

    current = client.get("/api/v1/world/phases/current").json()
    assert current["absolute_index"] == 0
    assert current["run_id"] is None

    events = client.get("/api/v1/world/events", params={"after": 0}).json()
    assert len(events["entries"]) == 1
    assert events["entries"][0]["sequence"] == 1
    assert events["entries"][0]["event_type"] == "world_seeded"
    assert events["next_after"] == 1
    empty = client.get("/api/v1/world/events", params={"after": 1}).json()
    assert empty["entries"] == [] and empty["next_after"] == 1


def test_event_pagination_rejects_bad_bounds(
    boundary: tuple[BoundaryClient, FakeGateway],
) -> None:
    client, _gateway = boundary
    client.post("/api/v1/world/seed")
    bad_after = client.get("/api/v1/world/events", params={"after": -1})
    assert bad_after.status_code == 422
    assert bad_after.json()["error"]["code"] == "VALIDATION_FAILED"
    bad_limit = client.get("/api/v1/world/events", params={"limit": 0})
    assert bad_limit.status_code == 422


def test_advance_requires_idempotency_key(
    boundary: tuple[BoundaryClient, FakeGateway],
) -> None:
    client, _gateway = boundary
    world_id = client.post("/api/v1/world/seed").json()["world_id"]
    response = client.post("/api/v1/world/phases/advance", json={"world_id": world_id})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_advance_replay_and_progress(boundary: tuple[BoundaryClient, FakeGateway]) -> None:
    client, gateway = boundary
    world_id = client.post("/api/v1/world/seed").json()["world_id"]
    gateway.enqueue_text("Dawn breaks over the Hearth.", 10, 5)
    gateway.enqueue_text("Morning comes to the market.", 10, 5)
    first = client.post(
        "/api/v1/world/phases/advance",
        json={"world_id": world_id},
        headers={"Idempotency-Key": "stage0-demo-advance-1"},
    )
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "completed"
    assert body["idempotent_replay"] is False
    assert body["world_version"] == 1
    assert body["event_cursor"] == 2
    assert body["result"]["sequence"] == 2

    task = client.get(f"/api/v1/operations/tasks/{body['task_id']}").json()
    assert task["state"] == "succeeded"
    assert task["owner"] is None
    assert task["kind"] == "phase_advance"

    replay = client.post(
        "/api/v1/world/phases/advance",
        json={"world_id": world_id},
        headers={"Idempotency-Key": "stage0-demo-advance-1"},
    )
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["event_cursor"] == 2
    assert replay.json()["result"] == body["result"]
    assert replay.json()["run_id"] == body["run_id"]

    second = client.post(
        "/api/v1/world/phases/advance",
        json={"world_id": world_id},
        headers={"Idempotency-Key": "stage0-demo-advance-2"},
    )
    assert second.json()["idempotent_replay"] is False
    assert second.json()["result"]["sequence"] == 3
    current = client.get("/api/v1/world/phases/current").json()
    assert current["absolute_index"] == 2


def test_advance_unknown_world_is_not_found(
    boundary: tuple[BoundaryClient, FakeGateway],
) -> None:
    client, _gateway = boundary
    response = client.post(
        "/api/v1/world/phases/advance",
        json={"world_id": "10000000-0000-4000-8000-000000009999"},
        headers={"Idempotency-Key": "stage0-demo-missing"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_unknown_task_is_not_found(boundary: tuple[BoundaryClient, FakeGateway]) -> None:
    client, _gateway = boundary
    response = client.get("/api/v1/operations/tasks/10000000-0000-4000-8000-000000009999")
    assert response.status_code == 404


def test_reconcile_reports_idle_world(boundary: tuple[BoundaryClient, FakeGateway]) -> None:
    client, gateway = boundary
    world_id = client.post("/api/v1/world/seed").json()["world_id"]
    gateway.enqueue_text("Dawn breaks.", 1, 1)
    client.post(
        "/api/v1/world/phases/advance",
        json={"world_id": world_id},
        headers={"Idempotency-Key": "stage0-demo-reconcile"},
    )
    report = client.post("/api/v1/operations/reconcile", json={"world_id": world_id}).json()
    assert report["open_run_id"] is None
    assert report["open_state"] is None


def test_error_status_mapping_is_stable() -> None:
    from worldsim.domain.errors import ErrorCode
    from worldsim.interfaces.http.errors import status_for

    assert status_for(ErrorCode.NOT_FOUND) == 404
    assert status_for(ErrorCode.FORBIDDEN) == 403
    assert status_for(ErrorCode.VERSION_CONFLICT) == 409
    assert status_for(ErrorCode.IDEMPOTENCY_CONFLICT) == 409
    assert status_for(ErrorCode.PRECONDITION_FAILED) == 409
    assert status_for(ErrorCode.VALIDATION_FAILED) == 422
    assert status_for(ErrorCode.UNSUPPORTED_ACTION) == 422
    assert status_for(ErrorCode.INVARIANT_VIOLATED) == 500


def test_openapi_matches_committed() -> None:
    app = create_app(Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS)
    generated = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    assert generated == OPENAPI.read_text(encoding="utf-8")
