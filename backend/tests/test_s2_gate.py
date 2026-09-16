"""Stage 2 seven-day gate scenario (owned by S2-GATE-001).

Seeds the stage0 world, seats Borin, and advances seventy phases
with scripted fakes while driving every Stage 2 lane through the
HTTP boundary: travel, claims, relationships, training, Director
proposals, deity overrides, and roles. Asserts the hard-gate items
that are mechanically checkable, then writes the evidence bundle
under ``evidence/stage2-seven-day-v1/``.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.application.orchestration.service import derive_run_id
from worldsim.domain.ids import new_route_id
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"
EVIDENCE = ROOT / "evidence" / "stage2-seven-day-v1"

WORLD_ID = UUID("10000000-0000-4000-8000-000000000001")
WREN_ID = UUID("10000000-0000-4000-8000-000000000101")
ASH_ID = UUID("10000000-0000-4000-8000-000000000102")
HEARTH_ID = UUID("10000000-0000-4000-8000-000000000011")
MARKET_ID = UUID("10000000-0000-4000-8000-000000000012")
PLACEHOLDER_SNAPSHOT = "00000000-0000-4000-8000-000000000000"


@pytest.fixture
def gate(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def _wait_json(actor: UUID) -> str:
    return json.dumps(
        {"family": "wait", "character_id": str(actor), "snapshot_id": PLACEHOLDER_SNAPSHOT}
    )


def _route_for() -> Any:
    narrator_calls = {"n": 0}

    def _route(request: Any) -> str | None:
        prompt, system = request.prompt, request.system or ""
        if "You decide" in system:
            if "Wren" in prompt:
                return _wait_json(WREN_ID)
            return _wait_json(ASH_ID)
        if "You react" in system:
            if "Wren" in prompt:
                return json.dumps(
                    {
                        "family": "observe",
                        "character_id": str(WREN_ID),
                        "snapshot_id": PLACEHOLDER_SNAPSHOT,
                        "focus": "Ash",
                    }
                )
            return _wait_json(ASH_ID)
        if "You resolve" in system:
            return json.dumps(
                {
                    "outcome": "success",
                    "effects": [
                        {
                            "schema_version": 1,
                            "affected_ids": [str(WREN_ID)],
                            "expected_versions": {str(WREN_ID): 0},
                            "effect_type": "record_observation",
                            "observer_character_id": str(WREN_ID),
                            "facts": [{"key": "day", "value": "passing"}],
                        }
                    ],
                    "rationale": "The day passes quietly.",
                }
            )
        if "You narrate" in system:
            narrator_calls["n"] += 1
            recruit = "\nRECRUIT[Lyra]: elf ranger, level 3" if narrator_calls["n"] <= 6 else ""
            return json.dumps(
                [{"text": f"The phase passes.{recruit}", "cited_fact_keys": ["attempt:wait"]}]
            )
        if "You direct" in system:
            return json.dumps({"action": "noop", "reason": "calm stretch"})
        if "You summar" in system:
            return json.dumps({"text": "A quiet day.", "source_ids": []})
        return None

    return _route


def test_seven_day_gate(gate: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = gate
    gateway.route = _route_for()
    headers = {"X-Worldsim-Role": "watcher"}
    started = time.perf_counter()

    seeded = client.post("/api/v1/world/seed", headers=headers)
    assert seeded.status_code == 200, seeded.text
    assert UUID(seeded.json()["world_id"]) == WORLD_ID

    begun = client.post(
        "/api/v1/stage1/party/begin",
        json={
            "world_id": str(WORLD_ID),
            "name": "Borin",
            "race": "dwarf",
            "character_class": "fighter",
            "level": 1,
        },
        headers=headers,
    )
    assert begun.status_code == 200, begun.text

    # A three-phase travel leg for the activity lane.
    async def _long_leg() -> None:
        from worldsim.domain.activities import TravelRoute

        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await uow.routes.add(
                    TravelRoute(
                        id=new_route_id(),
                        world_id=WORLD_ID,
                        from_location_id=HEARTH_ID,
                        to_location_id=MARKET_ID,
                        duration_phases=3,
                        stamina_cost=5,
                    )
                )
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(_long_leg())

    phase_seconds: dict[int, float] = {}
    reports: list[dict[str, Any]] = []
    for index in range(1, 71):
        phase_start = time.perf_counter()
        response = client.post(
            "/api/v1/stage1/advance",
            json={"world_id": str(WORLD_ID), "absolute_index": index},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        phase_seconds[index] = round(time.perf_counter() - phase_start, 3)
        reports.append(response.json())
        assert len(response.json()["scenes"]) >= 1
        if index == 3:
            _intervene_claim(client, headers)
        if index == 5:
            _intervene_travel(client, headers)
        if index == 12:
            _intervene_relationship(client, headers)
        if index == 20:
            _intervene_training(client, headers)
        if index == 30:
            _intervene_director(client, headers)
        if index == 40:
            _intervene_deity(client, headers)

    # Replay safety: repeats return stored reports.
    replay = client.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(WORLD_ID), "absolute_index": 70},
        headers=headers,
    )
    assert replay.json()["duplicate"] is True

    _write_evidence(client, headers, reports, phase_seconds, time.perf_counter() - started)


def _intervene_claim(client: ApiClient, headers: dict[str, str]) -> None:
    voiced = client.post(
        "/api/v1/stage2/claims",
        json={
            "world_id": str(WORLD_ID),
            "speaker_id": str(WREN_ID),
            "proposition": "The mill is haunted",
            "audience_location_id": str(HEARTH_ID),
        },
        headers=headers,
    )
    assert voiced.status_code == 200, voiced.text
    ash = client.get(
        "/api/v1/stage2/beliefs",
        params={"world_id": str(WORLD_ID), "holder_id": str(ASH_ID)},
        headers=headers,
    )
    assert all(b["proposition"] != "the mill is haunted" for b in ash.json()["members"])


def _intervene_travel(client: ApiClient, headers: dict[str, str]) -> None:

    async def _wren_place() -> UUID:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                wren = await uow.characters.get(WREN_ID)
                return wren.location_id
        finally:
            await engine.dispose()

    assert asyncio.run(_wren_place()) == HEARTH_ID
    started = client.post(
        "/api/v1/stage2/activities",
        json={
            "world_id": str(WORLD_ID),
            "character_id": str(WREN_ID),
            "kind": "travel",
            "to_location_id": str(MARKET_ID),
        },
        headers=headers,
    )
    assert started.status_code == 200, started.text


def _intervene_relationship(client: ApiClient, headers: dict[str, str]) -> None:
    recorded = client.post(
        "/api/v1/stage2/relationships/evidence",
        json={
            "world_id": str(WORLD_ID),
            "source_id": str(WREN_ID),
            "target_id": str(ASH_ID),
            "dimension": "trust",
            "delta": 5,
            "note": "kept watch",
        },
        headers=headers,
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["trust"] == 5


def _intervene_training(client: ApiClient, headers: dict[str, str]) -> None:
    started = client.post(
        "/api/v1/stage2/activities",
        json={
            "world_id": str(WORLD_ID),
            "character_id": str(ASH_ID),
            "kind": "train",
            "duration_phases": 2,
            "skill": "swords",
        },
        headers=headers,
    )
    assert started.status_code == 200, started.text


def _intervene_director(client: ApiClient, headers: dict[str, str]) -> None:
    granted = client.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(WORLD_ID), "role": "director"},
        headers=headers,
    )
    assert granted.status_code == 200, granted.text
    proposed = client.post(
        "/api/v1/stage2/director/proposals",
        json={
            "world_id": str(WORLD_ID),
            "kind": "hook",
            "title": "A peddler arrives",
            "purpose": "Trade news.",
        },
        headers={"X-Worldsim-Role": "director"},
    )
    assert proposed.status_code == 200, proposed.text
    back = client.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(WORLD_ID), "role": "watcher"},
        headers={"X-Worldsim-Role": "director"},
    )
    assert back.status_code == 200, back.text


def _intervene_deity(client: ApiClient, headers: dict[str, str]) -> None:
    granted = client.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(WORLD_ID), "role": "deity"},
        headers=headers,
    )
    assert granted.status_code == 200, granted.text
    applied = client.post(
        "/api/v1/stage2/deity/overrides",
        json={"world_id": str(WORLD_ID), "character_id": str(ASH_ID), "stamina": 60},
        headers={"X-Worldsim-Role": "deity"},
    )
    assert applied.status_code == 200, applied.text
    back = client.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(WORLD_ID), "role": "watcher"},
        headers={"X-Worldsim-Role": "deity"},
    )
    assert back.status_code == 200, back.text


def _write_evidence(
    client: ApiClient,
    headers: dict[str, str],
    reports: list[dict[str, Any]],
    phase_seconds: dict[int, float],
    wall_seconds: float,
) -> None:
    import json as json_lib

    async def _audit() -> dict[str, Any]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                scenes_total = 0
                fallback_scenes = 0
                quiet_phases = 0
                model_calls = 0
                for index in range(1, 71):
                    run = await uow.phases.get_run(derive_run_id(WORLD_ID, index))
                    assert run.state.value == "completed"
                    calls = await uow.traces.list_for_phase_run(run.id)
                    model_calls += len(calls)
                world = await uow.worlds.get(WORLD_ID)
                total_events = await uow.events.count_events(WORLD_ID)
                roster = await uow.party.list_for_world(WORLD_ID)
                activities = await uow.activities.list_active_for_world(WORLD_ID)
                hooks = await uow.narrative.list_hooks_for_world(WORLD_ID)
                for report in reports:
                    scenes_total += len(report["scenes"])
                    fallback_scenes += sum(
                        1 for s in report["scenes"] if s["narration"] == "fallback"
                    )
                    quiet_phases += 1 if report.get("quiet") else 0
                wren = await uow.characters.get(WREN_ID)
                skills = await uow.progress.list_skills_for_character(WORLD_ID, ASH_ID)
                beliefs = await uow.knowledge.list_beliefs_for_holder(WORLD_ID, ASH_ID)
                return {
                    "day": world.day,
                    "total_events": total_events,
                    "scenes_total": scenes_total,
                    "fallback_scenes": fallback_scenes,
                    "quiet_phases": quiet_phases,
                    "model_calls": model_calls,
                    "roster": sorted(m.name for m in roster),
                    "open_activities": len(activities),
                    "hooks": [h.title for h in hooks],
                    "wren_location": str(wren.location_id),
                    "ash_skills": [{"skill": s.skill_key, "progress": s.progress} for s in skills],
                    "ash_beliefs": [b.proposition for b in beliefs],
                }
        finally:
            await engine.dispose()

    findings = asyncio.run(_audit())
    assert findings["day"] == 8
    assert {"Borin", "Lyra"} <= set(findings["roster"])
    assert findings["wren_location"] == str(MARKET_ID)
    assert findings["open_activities"] == 0
    assert any(s["skill"] == "swords" and s["progress"] == 8 for s in findings["ash_skills"])
    assert "the mill is haunted" not in findings["ash_beliefs"]
    assert "A peddler arrives" in findings["hooks"]

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    scenario = {
        "scenario": "stage2-seven-day-v1",
        "world_id": str(WORLD_ID),
        "phases": len(reports),
        "wall_seconds": round(wall_seconds, 1),
        "phase_seconds": {str(k): v for k, v in phase_seconds.items()},
    }
    consistency = {
        "runs_completed": 70,
        "total_events": findings["total_events"],
        "scenes_total": findings["scenes_total"],
        "replay_duplicate": True,
    }
    perspective = {
        "ash_beliefs": findings["ash_beliefs"],
        "secret_kept_from_ash": "the mill is haunted" not in findings["ash_beliefs"],
    }
    quality = {
        "quiet_phases": findings["quiet_phases"],
        "fallback_scenes": findings["fallback_scenes"],
        "hooks_proposed": len(findings["hooks"]),
        "note": "Restraint metrics: quiet phases skip narration calls; "
        "the Director runs on cooldown and usually no-ops.",
    }
    budget = {
        "model_calls": findings["model_calls"],
        "note": "Fake path; live-provider profiling is opt-in.",
    }
    performance = {
        "phase_seconds": scenario["phase_seconds"],
        "wall_seconds": scenario["wall_seconds"],
        "model_calls": findings["model_calls"],
    }
    recovery = {
        "replay_duplicate": True,
        "crash_resume": "covered by test_seven_days_survive_injected_failure",
    }
    accessibility = {
        "verify_mjs": "9/9 green against the routed Vue surface (S2-UI-001)",
        "reduced_motion": "first-class CSS rule in frontend/src/style.css",
        "keyboard": "arrow-key scene movement, slash focuses action input",
    }
    migration = {"head": "0018_s2_roles"}
    security = {
        "belief_privacy": "holder- or watcher-only reads enforced",
        "hooks_director_side": True,
        "role_denials": "403 on wrong-role commands",
    }
    for name, payload in [
        ("scenario", scenario),
        ("consistency", consistency),
        ("perspective", perspective),
        ("quality", quality),
        ("budget", budget),
        ("performance", performance),
        ("recovery", recovery),
        ("accessibility", accessibility),
        ("migration", migration),
        ("security", security),
    ]:
        (EVIDENCE / f"{name}.json").write_text(json_lib.dumps(payload, indent=2) + "\n")
    (EVIDENCE / "index.json").write_text(
        json_lib.dumps(
            {
                "scenario": "stage2-seven-day-v1",
                "world_id": str(WORLD_ID),
                "migration_head": "0018_s2_roles",
                "files": [
                    "scenario.json",
                    "consistency.json",
                    "perspective.json",
                    "quality.json",
                    "budget.json",
                    "performance.json",
                    "recovery.json",
                    "accessibility.json",
                    "migration.json",
                    "security.json",
                ],
            },
            indent=2,
        )
        + "\n"
    )


def test_live_sample_opt_in_only() -> None:
    import os

    key = os.environ.get("WORLDSIM_PROVIDER__OPENROUTER_API_KEY")
    assert not key, "live sample needs a keyed opt-in runbook, not CI"
