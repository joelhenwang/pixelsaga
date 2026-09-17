"""Bounded live-provider sample (owned by S3-PROV-001).

Skipped without WORLDSIM_LIVE_SCENARIO=1 and real credentials;
see docs/LIVE_RUNBOOK.md. Three phases on the stage0 seed with
every role live, then the evidence bundle with usage/cost rows.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from worldsim.application.orchestration.service import derive_run_id
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"
EVIDENCE = ROOT / "evidence" / "stage3-live-v1"

WORLD_ID = UUID("10000000-0000-4000-8000-000000000001")

LIVE = os.environ.get("WORLDSIM_LIVE_SCENARIO") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="live sample needs opt-in and credentials")


def test_three_phases_live(migrated_db: None) -> None:
    settings = Settings()
    assert settings.provider.active_profile == "openrouter"
    app = create_app(
        settings,
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
    )
    headers = {"X-Worldsim-Role": "watcher"}
    with TestClient(app) as raw:
        seeded = raw.post("/api/v1/world/seed", headers=headers)
        assert seeded.status_code == 200, seeded.text
        wren_id = "10000000-0000-4000-8000-000000000101"
        ash_id = "10000000-0000-4000-8000-000000000102"
        zero = "00000000-0000-4000-8000-000000000000"
        for index in range(1, 4):
            intents = {}
            if index == 2:
                intents = {
                    wren_id: {
                        "family": "communicate",
                        "character_id": wren_id,
                        "snapshot_id": zero,
                        "target_character_id": ash_id,
                        "topic": "the road north looks quiet today",
                    }
                }
            response = raw.post(
                "/api/v1/stage1/advance",
                json={
                    "world_id": str(WORLD_ID),
                    "absolute_index": index,
                    "player_intents": intents,
                },
                headers=headers,
            )
            assert response.status_code == 200, response.text

    async def _audit() -> dict[str, object]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                calls: list[dict[str, object]] = []
                phases: list[dict[str, object]] = []
                for index in range(1, 4):
                    run = await uow.phases.get_run(derive_run_id(WORLD_ID, index))
                    assert run.state.value == "completed"
                    beats: list[str] = []
                    for scene in await uow.scenes.list_for_run(run.id):
                        if scene.event_id is None:
                            continue
                        for beat in await uow.scenes.narrations_for_event(scene.event_id):
                            beats.append(beat.text)
                    phases.append({"absolute_index": index, "beats": beats})
                    for call in await uow.traces.list_for_phase_run(run.id):
                        if call.status != "succeeded":
                            calls.append(
                                {
                                    "role": call.role,
                                    "status": call.status,
                                    "error": call.error_code,
                                }
                            )
                            continue
                        cost = await uow.costs.get_for_call(call.id)
                        assert cost is not None, f"call {call.id} has no cost row"
                        calls.append(
                            {
                                "role": call.role,
                                "status": call.status,
                                "profile": call.profile_name,
                                "prompt_tokens": call.prompt_tokens,
                                "completion_tokens": call.completion_tokens,
                                "model": cost.model,
                                "pricing_version": cost.pricing_version,
                                "prompt_cost_usd": cost.prompt_cost_usd,
                                "completion_cost_usd": cost.completion_cost_usd,
                                "estimated": cost.estimated,
                            }
                        )
                total = await uow.costs.total_for_world(WORLD_ID)
                return {"calls": calls, "total_cost_usd": total, "phases": phases}
        finally:
            await engine.dispose()

    findings = asyncio.run(_audit())
    assert findings["calls"]
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "scenario.json").write_text(
        json.dumps(
            {
                "scenario": "stage3-live-v1",
                "world_id": str(WORLD_ID),
                "phases": 3,
                "profile": settings.provider.active_profile,
            },
            indent=2,
        )
        + "\n"
    )
    (EVIDENCE / "calls.json").write_text(json.dumps(findings, indent=2) + "\n")
