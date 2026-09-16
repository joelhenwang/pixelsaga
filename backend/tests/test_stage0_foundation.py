"""S0-GATE-001: stage0-foundation-v1 deterministic demonstration (owned by S0-GATE-001).

Twelve steps from section 4 of the execution plan against the real
boundary and services: seed, inspect, advance with a fixed key, fault
after commit, restart, reconcile, replay the same key, prove no new
rows, then audit. Pass/fail plus a generated evidence bundle under
``evidence/stage0-foundation-v1/``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from worldsim.application.operations.consistency import audit_world
from worldsim.application.orchestration.service import PhaseOrchestrator
from worldsim.application.tasks.service import TaskService
from worldsim.application.tracing.service import TraceService
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.domain.enums import PhaseRunState
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import (
    SqlAlchemyUnitOfWork,
    create_unit_of_work,
)
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.tracing.langsmith import NullExporter
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"
EVIDENCE = ROOT / "evidence" / "stage0-foundation-v1"

SENTINELS = ("sentinel-gate-key-1", "sentinel-gate-key-2")


class _Crash(Exception):
    pass


def _hook_point(target: str):  # type: ignore[no-untyped-def]
    fired: dict[str, str | None] = {"point": None}

    def _hook(point: str) -> None:
        if point == target and fired["point"] is None:
            fired["point"] = point
            raise _Crash(f"termination at {point}")

    return _hook


def _orchestrator(
    engine: AsyncEngine,
    gateway: FakeGateway,
    hook: Callable[[str], None] | None = None,
) -> PhaseOrchestrator:
    def _factory() -> SqlAlchemyUnitOfWork:
        return create_unit_of_work(engine)

    return PhaseOrchestrator(
        _factory,
        CanonicalTransaction(_factory),
        TaskService(_factory),
        TraceService(_factory, NullExporter()),
        gateway,
        fault_hook=hook,
    )


async def _counts(engine: AsyncEngine, world_id: UUID) -> dict[str, int]:
    def _factory() -> SqlAlchemyUnitOfWork:
        return create_unit_of_work(engine)

    async with _factory() as uow:
        events = await uow.events.count_events(world_id)
        outbox = await uow.outbox.count_pending(world_id)
        world = await uow.worlds.get(world_id)
        characters = await uow.characters.list_for_world(world_id)
        observations = 0
        for event in await uow.events.list_range(world_id, 0, events + 1):
            observations += len(await uow.perception.observations_for_event(event.id))
    return {
        "events": events,
        "outbox": outbox,
        "world_version": world.version,
        "characters": len(characters),
        "observations": observations,
    }


async def _applied_head(engine: AsyncEngine) -> str | None:
    async with engine.connect() as connection:
        value = (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one_or_none()
    return str(value) if value is not None else None


def _script_heads() -> list[str]:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    return list(ScriptDirectory.from_config(config).get_heads())


def test_stage0_foundation_v1(migrated_db: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORLDSIM_SECURITY__API_KEY", SENTINELS[0])
    monkeypatch.setenv("WORLDSIM_PROVIDER__OPENROUTER_API_KEY", SENTINELS[1])

    async def _inner() -> dict[str, object]:
        settings = Settings()
        engine = create_engine(settings)
        steps: list[dict[str, object]] = []
        try:
            gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
            app = create_app(
                settings,
                seed_dir=SEED_DIR,
                migrations_dir=MIGRATIONS,
                gateway_factory=lambda: gateway,
            )
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://stage0") as client:
                seeded = (await client.post("/api/v1/world/seed")).json()
                assert seeded["duplicate"] is False
                world_id = UUID(seeded["world_id"])
                steps.append({"name": "seed", "world_id": str(world_id)})

                world = (await client.get("/api/v1/world")).json()
                clock = (await client.get("/api/v1/world/clock")).json()
                timeline = (await client.get("/api/v1/world/events", params={"after": 0})).json()
                assert world["name"] == "Ember Vale"
                assert clock["absolute_index"] == 0
                assert timeline["next_after"] == 1
                steps.append({"name": "inspect", "clock": clock, "cursor": 1})

                gateway.enqueue_text("Dawn breaks over the Hearth.", 10, 5)
                first = (
                    await client.post(
                        "/api/v1/world/phases/advance",
                        json={"world_id": str(world_id)},
                        headers={"Idempotency-Key": "stage0-foundation-k1"},
                    )
                ).json()
                assert first["idempotent_replay"] is False
                assert first["result"]["sequence"] == 2
                steps.append(
                    {
                        "name": "advance-k1",
                        "sequence": 2,
                        "run_id": first["run_id"],
                        "event_id": first["result"]["event_id"],
                    }
                )

                def _factory():  # type: ignore[no-untyped-def]
                    return create_unit_of_work(engine)

                async with _factory() as uow:
                    tick = await uow.events.get_event(UUID(first["result"]["event_id"]))
                    observations = await uow.perception.observations_for_event(tick.id)
                    families = {
                        fact.value
                        for observation in observations
                        for fact in observation.facts
                        if fact.key == "intent_family"
                    }
                    assert families == {"wait"}
                steps.append({"name": "scripted-intents", "families": sorted(families)})

                gateway.enqueue_text("Morning comes to the market.", 10, 5)
                crashing = _orchestrator(engine, gateway, _hook_point("after_tick_committed"))
                with pytest.raises(_Crash):
                    await crashing.advance_world(world_id, "stage0-foundation-k2")
                mid_counts = await _counts(engine, world_id)
                assert mid_counts["events"] == 3
                steps.append({"name": "fault-after-commit", "events": mid_counts["events"]})

                restarted = _orchestrator(engine, gateway)
                reconciled = await restarted.reconcile_world(world_id)
                assert reconciled.open_state == PhaseRunState.RETRYABLE_FAILED.value
                steps.append(
                    {
                        "name": "restart-reconcile",
                        "open_state": reconciled.open_state,
                        "tasks_requeued": reconciled.tasks_requeued,
                    }
                )

                replay = (
                    await client.post(
                        "/api/v1/world/phases/advance",
                        json={"world_id": str(world_id)},
                        headers={"Idempotency-Key": "stage0-foundation-k2"},
                    )
                ).json()
                assert replay["idempotent_replay"] is True
                assert replay["result"]["sequence"] == 3
                replay_counts = await _counts(engine, world_id)
                assert replay_counts["events"] == 3
                steps.append(
                    {
                        "name": "replay-k2",
                        "sequence": 3,
                        "events": replay_counts["events"],
                    }
                )

                gateway.enqueue_text("Noon settles over the market.", 10, 5)
                third = (
                    await client.post(
                        "/api/v1/world/phases/advance",
                        json={"world_id": str(world_id)},
                        headers={"Idempotency-Key": "stage0-foundation-k3"},
                    )
                ).json()
                assert third["idempotent_replay"] is False
                assert third["result"]["sequence"] == 4
                final_counts = await _counts(engine, world_id)
                assert final_counts["events"] == 4
                assert final_counts["world_version"] == 3
                steps.append(
                    {
                        "name": "advance-k3",
                        "sequence": 4,
                        "counts": final_counts,
                    }
                )

                report = await audit_world(_factory, world_id)
                assert report.clean, [vars(v) for v in report.violations]
                steps.append({"name": "consistency-audit", "checks": report.checks_run})

                ready = (await client.get("/api/v1/health/ready")).json()
                assert ready["status"] in ("ready", "degraded")
                heads = _script_heads()
                applied = await _applied_head(engine)
                assert heads == [applied]
                steps.append(
                    {
                        "name": "migration-report",
                        "heads": heads,
                        "applied": applied,
                    }
                )
            return {"world_id": str(world_id), "steps": steps}
        finally:
            await engine.dispose()

    outcome = asyncio.run(_inner())
    world_id = UUID(str(outcome["world_id"]))
    evidence = {
        "scenario": "stage0-foundation-v1",
        "world_id": str(world_id),
        "steps": outcome["steps"],
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "scenario.json").write_text(json.dumps(evidence, indent=2) + "\n")

    scanned = sorted(EVIDENCE.glob("*.json")) + [
        ROOT / "content" / "schemas" / "openapi.json",
        ROOT / "content" / "schemas" / "domain-schema.json",
    ]
    for path in scanned:
        text = path.read_text(encoding="utf-8")
        for sentinel in SENTINELS:
            assert sentinel not in text, f"sentinel leaked into {path}"
    (EVIDENCE / "security.json").write_text(
        json.dumps(
            {
                "scanned": [str(path) for path in scanned],
                "sentinels_tested": len(SENTINELS),
                "clean": True,
            },
            indent=2,
        )
        + "\n"
    )
    (EVIDENCE / "index.json").write_text(
        json.dumps(
            {
                "scenario": "stage0-foundation-v1",
                "world_id": str(world_id),
                "migration_head": "0010_dnd_monsters",
                "seed_version": "stage0-v1",
                "files": ["scenario.json", "security.json", "index.json"],
            },
            indent=2,
        )
        + "\n"
    )
