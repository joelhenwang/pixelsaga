"""Stage 3 quality metrics and baselines (owned by S3-QUAL-001).

Math unit tests plus two integration runs (30 phases, 70 phases)
that compute per-phase metrics from committed rows and commit the
rollup to docs/stage3-quality-baseline-v1.json. No gates on values.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.application.orchestration.service import derive_run_id
from worldsim.application.quality.metrics import diversity, phase_metrics, repetition
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"
BASELINE = ROOT / "docs" / "stage3-quality-baseline-v1.json"

WORLD_ID = UUID("10000000-0000-4000-8000-000000000001")
WREN_ID = UUID("10000000-0000-4000-8000-000000000101")
ASH_ID = UUID("10000000-0000-4000-8000-000000000102")
PLACEHOLDER_SNAPSHOT = "00000000-0000-4000-8000-000000000000"


def test_repetition_math() -> None:
    assert repetition([]) == 0.0
    assert repetition(["hello"]) == 0.0
    assert repetition(["the mill stands", "the mill stands"]) > 0.0
    assert repetition(["the mill stands", "rivers run cold"]) == 0.0
    assert repetition(["Hello, WORLD!", "hello world"]) == pytest.approx(0.5)


def test_diversity_math() -> None:
    assert diversity([], 2) == 0.0
    assert diversity(["a"], 0) == 0.0
    assert diversity(["attempt:wait", "attempt:wait"], 2) == 0.5
    assert diversity(["a", "b", "c"], 2) == 1.5


def test_phase_metrics_frozen_shape() -> None:
    metrics = phase_metrics(["a b", "a b"], ["k"], 2, 1, 0, 0)
    assert set(metrics) == {"repetition", "diversity", "fallback_rate", "director_creations"}
    assert metrics["fallback_rate"] == 0.5
    assert metrics["director_creations"] == 0


@pytest.fixture
def qual(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
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
            return _wait_json(WREN_ID if "Wren" in prompt else ASH_ID)
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
        if "You summar" in system or "You distill" in system:
            return json.dumps({"text": "A quiet day.", "source_ids": []})
        return None

    return _route


def _run_scenario(
    client: ApiClient, gateway: FakeGateway, phases: int
) -> dict[int, dict[str, Any]]:
    headers = {"X-Worldsim-Role": "watcher"}
    gateway.route = _route_for()
    assert client.post("/api/v1/world/seed", headers=headers).status_code == 200
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
    reports: dict[int, dict[str, Any]] = {}
    for index in range(1, phases + 1):
        response = client.post(
            "/api/v1/stage1/advance",
            json={"world_id": str(WORLD_ID), "absolute_index": index},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        reports[index] = response.json()
    return reports


def _audit_quality(reports: dict[int, dict[str, Any]]) -> dict[str, Any]:
    async def _audit() -> dict[str, Any]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                per_phase: dict[str, dict[str, float]] = {}
                hooks = await uow.narrative.list_hooks_for_world(WORLD_ID)
                arcs = await uow.narrative.list_arcs_for_world(WORLD_ID)
                hooks_by_phase: dict[int, int] = {}
                arcs_by_phase: dict[int, int] = {}
                for row in hooks:
                    hooks_by_phase[row.created_phase_index] = (
                        hooks_by_phase.get(row.created_phase_index, 0) + 1
                    )
                for row in arcs:
                    arcs_by_phase[row.created_phase_index] = (
                        arcs_by_phase.get(row.created_phase_index, 0) + 1
                    )
                for index, report in reports.items():
                    run = await uow.phases.get_run(derive_run_id(WORLD_ID, index))
                    scenes = await uow.scenes.list_for_run(run.id)
                    texts: list[str] = []
                    cited: list[str] = []
                    for scene in scenes:
                        if scene.event_id is None:
                            continue
                        for beat in await uow.scenes.narrations_for_event(scene.event_id):
                            texts.append(beat.text)
                            cited.extend(beat.cited_fact_keys)
                    fallback = sum(1 for s in report["scenes"] if s["narration"] == "fallback")
                    per_phase[str(index)] = phase_metrics(
                        texts,
                        cited,
                        len(scenes),
                        fallback,
                        hooks_by_phase.get(index, 0),
                        arcs_by_phase.get(index, 0),
                    )
                return {"per_phase": per_phase, "hooks": len(hooks), "arcs": len(arcs)}
        finally:
            await engine.dispose()

    return asyncio.run(_audit())


def _rollup(
    name: str, phases: int, reports: dict[int, dict[str, Any]], audit: dict[str, Any]
) -> dict[str, Any]:
    series = audit["per_phase"]
    reps = [m["repetition"] for m in series.values()]
    divs = [m["diversity"] for m in series.values()]
    quiet = sum(1 for r in reports.values() if r.get("quiet")) / phases
    creations = sum(m["director_creations"] for m in series.values())
    return {
        "scenario": name,
        "phases": phases,
        "mean_repetition": round(sum(reps) / len(reps), 4),
        "mean_diversity": round(sum(divs) / len(divs), 4),
        "quiet_ratio": round(quiet, 4),
        "director_creations": creations,
        "director_noop_rate": round(1 - creations / phases, 4),
        "per_phase": series,
    }


def test_thirty_phase_quality_baseline(qual: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = qual
    reports = _run_scenario(client, gateway, 30)
    audit = _audit_quality(reports)
    rollup = _rollup("stage3-quality-30", 30, reports, audit)
    assert len(rollup["per_phase"]) == 30
    assert all(0.0 <= m["repetition"] <= 1.0 for m in rollup["per_phase"].values())
    _record_baseline("thirty_phase", rollup)


def test_seven_day_quality_baseline(qual: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = qual
    reports = _run_scenario(client, gateway, 70)
    audit = _audit_quality(reports)
    rollup = _rollup("stage3-quality-70", 70, reports, audit)
    assert len(rollup["per_phase"]) == 70
    _record_baseline("seven_day", rollup)


def _record_baseline(section: str, rollup: dict[str, Any]) -> None:
    baseline: dict[str, Any] = {}
    if BASELINE.exists():
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline[section] = rollup
    baseline["definitions"] = {
        "repetition": "1 - distinct/total word bigrams over phase beats (n=2)",
        "diversity": "distinct cited keys over scenes",
        "fallback_rate": "fallback scenes over scenes",
        "quiet_ratio": "quiet phases over phases",
        "director_creations": "hooks+arcs created in phase",
        "director_noop_rate": "1 - creations/phases",
    }
    BASELINE.write_text(json.dumps(baseline, indent=2) + "\n")
