"""Revamp P06: single-writer admission, idempotent replay, status lookup."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import httpx
from test_stage1_api import _route_for, _seed_two  # pyright: ignore[reportPrivateUsage]

from worldsim.application.execution import admit, new_owner, phase_scope, release
from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
from worldsim.domain.errors import DomainError
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


def _watcher() -> dict[str, str]:
    return {"X-Worldsim-Role": "watcher"}


def test_slot_admits_one_owner(migrated_db: None) -> None:
    async def _inner_slot() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            world = new_world_id()
            async with factory() as uow:
                await uow.worlds.add(World(id=world, name="Slot", seed_version="p06"))
                await uow.commit()
            first = await admit(factory, world, phase_scope(1), new_owner("t"))
            try:
                await admit(factory, world, phase_scope(1), new_owner("t"))
                raise AssertionError("second admission should conflict")
            except DomainError as error:
                assert error.details["run_id"] is None
            assert first.lease is not None
            await release(factory, first, first.lease.owner, True)
            second = await admit(factory, world, phase_scope(1), new_owner("t"))
            assert second.lease is not None
            await release(factory, second, second.lease.owner, True)
        finally:
            await engine.dispose()

    asyncio.run(_inner_slot())


def test_failed_slot_requeues(migrated_db: None) -> None:
    async def _inner_requeue() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            world = new_world_id()
            async with factory() as uow:
                await uow.worlds.add(World(id=world, name="Slot", seed_version="p06"))
                await uow.commit()
            slot = await admit(factory, world, phase_scope(1), new_owner("t"))
            assert slot.lease is not None
            await release(factory, slot, slot.lease.owner, False)
            async with factory() as uow:
                task = await uow.tasks.get(slot.id)
            assert task.state != "succeeded"
        finally:
            await engine.dispose()

    asyncio.run(_inner_requeue())

def test_concurrent_advance_executes_once(migrated_db: None) -> None:
    async def _inner_race() -> None:
        settings = Settings()
        ids = await _seed_two()
        snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
        base = _route_for(ids, snapshots)

        def slow(request: Any) -> Any:
            if "You decide" in (request.system or ""):
                time.sleep(2.5)
            return base(request)

        gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
        gateway.route = slow
        app = create_app(
            settings,
            seed_dir=SEED_DIR,
            migrations_dir=MIGRATIONS,
            gateway_factory=lambda: gateway,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://p06") as client:
            body = {"world_id": str(ids["world"]), "absolute_index": 1}
            first, second = await asyncio.gather(
                client.post("/api/v1/stage1/advance", json=body, headers=_watcher()),
                client.post("/api/v1/stage1/advance", json=body, headers=_watcher()),
            )
            codes = sorted([first.status_code, second.status_code])
            assert codes == [200, 409], (first.text, second.text)
            loser = first if first.status_code == 409 else second
            assert loser.json()["error"]["code"] == "VERSION_CONFLICT"
            winner = second if loser is first else first
            assert winner.json()["duplicate"] is False

            status = await client.get(
                "/api/v1/simulation/status",
                params={"world_id": str(ids["world"])},
                headers=_watcher(),
            )
            assert status.status_code == 200, status.text
            assert status.json()["latest_run_state"] == "completed"

            replay = await client.post("/api/v1/stage1/advance", json=body, headers=_watcher())
            assert replay.status_code == 200, replay.text
            assert replay.json()["duplicate"] is True
    asyncio.run(_inner_race())
