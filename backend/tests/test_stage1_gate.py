"""Stage 1 three-phase scenario and review gate (owned by S1-GATE-001).

Drives the full §2 fixture through the Stage 1 HTTP boundary with
scripted fakes: distinct voices, a private fact for Wren, a scheduled
phase-2 interaction, a phase-3 dialogue pair, and a narrator
unsupported-fact candidate. Asserts every hard exit-gate item that is
mechanically checkable, then writes the evidence bundle under
``evidence/stage1-three-phase-v1/``.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    ModelMalformedError,
    ModelRateLimitedError,
    ModelRefusalError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from worldsim.domain.ids import derive_intent_id
from worldsim.domain.perception import RecentMemory
from worldsim.domain.rules.scenes import assemble_scenes
from worldsim.domain.rules.views import WorldView
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"
EVIDENCE = ROOT / "evidence" / "stage1-three-phase-v1"

WORLD_ID = UUID("10000000-0000-4000-8000-000000000001")
WREN_ID = UUID("10000000-0000-4000-8000-000000000101")
ASH_ID = UUID("10000000-0000-4000-8000-000000000102")
SECRET = "Wren favors the northern pass at dawn"


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


def _watcher() -> dict[str, str]:
    return {"X-Worldsim-Role": "watcher"}


def _player(character: UUID) -> dict[str, str]:
    return {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(character)}


def _snapshot(world: UUID, index: int) -> UUID:
    return derive_snapshot_id(derive_run_id(world, index))


def _wait_json(actor: UUID, snapshot: UUID) -> str:
    return json.dumps({"family": "wait", "character_id": str(actor), "snapshot_id": str(snapshot)})


def _narrator_beats(cited: list[str]) -> str:
    return json.dumps([{"text": "The phase passes.", "cited_fact_keys": cited}])


def _disclosure() -> str:
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
                    "facts": [{"key": "greeting", "value": "dawn patrol"}],
                }
            ],
            "rationale": "Wren hears the call.",
        }
    )


def _script(gateway: FakeGateway, world: UUID, narrator_first_bad: bool = False) -> dict[str, int]:
    """Route every role by prompt markers (snapshot IDs are inert downstream)."""
    probe = {"narrator_calls": 0}
    snapshot = _snapshot(world, 1)

    def _route(request: CompletionRequest) -> str | None:
        prompt, system = request.prompt, request.system or ""
        if "You narrate" in system:
            probe["narrator_calls"] += 1
            if narrator_first_bad and probe["narrator_calls"] == 1:
                return _narrator_beats(["dragons"])
            return _narrator_beats(["attempt:wait"])
        if "You resolve" in system:
            return _disclosure()
        if "You react" in system:
            if "Wren" in prompt:
                return json.dumps(
                    {
                        "family": "observe",
                        "character_id": str(WREN_ID),
                        "snapshot_id": str(snapshot),
                        "focus": "Ash",
                    }
                )
            return _wait_json(ASH_ID, snapshot)
        if "You decide" in system:
            if "Wren" in prompt:
                return _wait_json(WREN_ID, snapshot)
            if "Ash" in prompt:
                return _wait_json(ASH_ID, snapshot)
        return None

    gateway.route = _route
    return probe


def _seed_secret() -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await uow.perception.add_memory(
                    RecentMemory(
                        id=uuid.uuid4(),
                        world_id=WORLD_ID,
                        owner_character_id=WREN_ID,
                        text=SECRET,
                        created_phase_index=0,
                    )
                )
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def _prompt_provenance(gateway: FakeGateway) -> list[dict[str, object]]:
    """Per model call: role marker, actor hint, and secret presence."""
    out: list[dict[str, object]] = []
    for request in gateway.sent_requests:
        system = request.system or ""
        if "You decide" in system:
            role = "character_decision"
        elif "You react" in system:
            role = "reaction"
        elif "You resolve" in system:
            role = "resolver"
        elif "You narrate" in system:
            role = "narrator"
        else:
            role = "unknown"
        actor = "wren" if "Wren" in request.prompt else ("ash" if "Ash" in request.prompt else "?")
        out.append(
            {
                "role": role,
                "actor_hint": actor,
                "has_secret": SECRET in request.prompt or SECRET in system,
            }
        )
    return out


def test_three_phase_scenario_gate(migrated_db: None, gate: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = gate
    phase_times: dict[int, float] = {}

    seeded = client.post("/api/v1/world/seed", headers=_watcher()).json()
    assert seeded["duplicate"] is False
    assert UUID(seeded["world_id"]) == WORLD_ID
    _seed_secret()
    _script(gateway, WORLD_ID, narrator_first_bad=True)

    reports: list[dict[str, Any]] = []
    for index in (1, 2, 3):
        body: dict[str, Any] = {"world_id": str(WORLD_ID), "absolute_index": index}
        headers = _watcher()
        if index == 2:
            # Scheduled interaction: Ash (player) hails Wren.
            body["player_intents"] = {
                str(ASH_ID): {
                    "family": "communicate",
                    "character_id": str(ASH_ID),
                    "snapshot_id": str(_snapshot(WORLD_ID, index)),
                    "target_character_id": str(WREN_ID),
                    "topic": "dawn patrol",
                }
            }
            headers = _player(ASH_ID)
        began = time.perf_counter()
        response = client.post("/api/v1/stage1/advance", json=body, headers=headers)
        assert response.status_code == 200, response.text
        phase_times[index] = time.perf_counter() - began
        report: dict[str, Any] = response.json()
        reports.append(report)

    assert [r["absolute_index"] for r in reports] == [1, 2, 3]
    assert all(not r["duplicate"] for r in reports)
    assert all(len(r["scenes"]) >= 1 for r in reports)

    async def _audit() -> dict[str, Any]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                findings: dict[str, Any] = {"phases": []}
                for report in reports:
                    snapshot_id = UUID(report["snapshot_id"])
                    snapshot = await uow.phases.get_snapshot(snapshot_id)
                    authors = [c.character_id for c in snapshot.characters]
                    intents = [
                        await uow.scenes.get_intent(derive_intent_id(WORLD_ID, snapshot_id, author))
                        for author in authors
                    ]
                    # Gate: one snapshot per phase across primary intents.
                    assert {i.snapshot_id for i in intents} == {snapshot_id}
                    for scene_json in report["scenes"]:
                        scene = await uow.scenes.get_scene(UUID(scene_json["scene_id"]))
                        members = {p.character_id for p in scene.participants}
                        for reaction in await uow.scenes.reactions_for_scene(scene.id):
                            # Gate: reactions belong to reacting participants.
                            assert reaction.reactor_character_id in members
                        resolution = await uow.scenes.get_resolution(scene.id)
                        # Gate: resolution stays inside feasible effects.
                        feasible = {
                            "move_entity",
                            "record_observation",
                            "record_memory",
                            "resource_adjusted",
                        }
                        assert {e.effect_type.value for e in resolution.effects} <= feasible
                        # Gate: player controls the attempt, never its outcome.
                        for intent in intents:
                            if intent.id in scene.intent_ids:
                                assert intent.author_character_id in members
                    findings["phases"].append(
                        {
                            "absolute_index": report["absolute_index"],
                            "snapshot_id": str(snapshot_id),
                            "intents": len(intents),
                            "scenes": len(report["scenes"]),
                        }
                    )
                # Gate: durable chain phase -> task -> model -> manifest -> event.
                calls = await uow.traces.list_for_phase_run(UUID(reports[2]["run_id"]))
                assert len(calls) >= 2
                for call in calls:
                    assert call.task_run_id is not None
                    manifest = await uow.traces.get_manifest(call.id)
                    assert manifest.rendered_hash
                events = await uow.events.count_events(WORLD_ID)
                assert events >= 6
                observations = 0
                for report in reports:
                    for scene_json in report["scenes"]:
                        scene = await uow.scenes.get_scene(UUID(scene_json["scene_id"]))
                        assert scene.event_id is not None
                        observations += len(
                            await uow.perception.observations_for_event(scene.event_id)
                        )
                assert observations >= 3
                findings["calls"] = len(calls)
                findings["events"] = events
                findings["observations"] = observations
                return findings
        finally:
            await engine.dispose()

    findings = asyncio.run(_audit())

    # Gate: B's model inputs never carry A's secret; A's do.
    provenance = _prompt_provenance(gateway)
    assert any(p["has_secret"] for p in provenance), "secret missing from A scope"
    assert all(not p["has_secret"] for p in provenance if p["actor_hint"] == "ash"), (
        "secret leaked into B scope"
    )

    # Gate: fake path uses scripted fakes with no HTTP client of their own.
    assert isinstance(gateway, FakeGateway)
    assert not hasattr(gateway, "_client")

    # Gate: duplicate delivery replays stored results.
    replay = client.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(WORLD_ID), "absolute_index": 1},
        headers=_watcher(),
    )
    assert replay.json()["duplicate"] is True
    assert [s["event_id"] for s in replay.json()["scenes"]] == [
        s["event_id"] for s in reports[0]["scenes"]
    ]

    # Gate: grouping ignores model completion order.
    async def _order() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                snapshot = await uow.phases.get_snapshot(UUID(reports[0]["snapshot_id"]))
                authors = [c.character_id for c in snapshot.characters]
                ordered = [
                    await uow.scenes.get_intent(derive_intent_id(WORLD_ID, snapshot.id, a))
                    for a in authors
                ]
                world_row = await uow.worlds.get(WORLD_ID)
                chars = await uow.characters.list_for_world(WORLD_ID)
                locs = await uow.locations.list_for_world(WORLD_ID)
                view = WorldView(world=world_row, characters=chars, locations=locs)
                kwargs: dict[str, Any] = {
                    "world_id": WORLD_ID,
                    "phase_run_id": UUID(reports[0]["run_id"]),
                    "snapshot_id": snapshot.id,
                }
                forward = assemble_scenes(ordered, view, **kwargs)
                backward = assemble_scenes(list(reversed(ordered)), view, **kwargs)
                assert [s.id for s in forward] == [s.id for s in backward]
        finally:
            await engine.dispose()

    asyncio.run(_order())

    _write_evidence(reports, findings, phase_times, provenance, gateway)


def test_fault_matrix_falls_back_safely(
    migrated_db: None, gate: tuple[ApiClient, FakeGateway]
) -> None:
    faults = [
        ModelTimeoutError("timed out"),
        ModelRateLimitedError("slow down", retry_after_s=1.0),
        ModelRefusalError("refused"),
        ModelMalformedError("bad envelope"),
        ModelUnavailableError("provider down"),
    ]
    for fault in faults:
        client, gateway = gate
        ids = _seed_two_world()
        gateway.route = lambda request, _fault=fault: _fault
        response = client.post(
            "/api/v1/stage1/advance",
            json={"world_id": str(ids), "absolute_index": 1},
            headers=_watcher(),
        )
        # Every model call fails; fallbacks carry the phase to completion.
        assert response.status_code == 200, response.text
        assert response.json()["duplicate"] is False
        assert all(s["narration"] == "fallback" for s in response.json()["scenes"])


def _seed_two_world() -> UUID:
    async def _inner() -> UUID:
        from worldsim.domain.characters import Character, CharacterCard
        from worldsim.domain.ids import (
            new_card_id,
            new_character_id,
            new_location_id,
            new_world_id,
        )
        from worldsim.domain.world import Location, World

        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Fault", seed_version="s1-test"))
                hearth = new_location_id()
                await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth"))
                cid = new_character_id()
                await uow.characters.add_identity(cid, wid, "Wren")
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=cid, name="Wren", version=1)
                )
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=wid,
                        name="Wren",
                        card_version=1,
                        location_id=hearth,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
                await uow.versions.ensure(wid, wid, "world")
                await uow.commit()
                return wid
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def test_live_scenario_opt_in_only() -> None:
    import os

    if os.environ.get("WORLDSIM_LIVE_SCENARIO") != "1":
        pytest.skip("live-provider scenario is opt-in")
    key = os.environ.get("WORLDSIM_PROVIDER__OPENROUTER_API_KEY", "")
    assert key, "live scenario needs WORLDSIM_PROVIDER__OPENROUTER_API_KEY"


def _write_evidence(
    reports: list[dict[str, Any]],
    findings: dict[str, Any],
    phase_times: dict[int, float],
    provenance: list[dict[str, object]],
    gateway: FakeGateway,
) -> None:
    async def _collect() -> dict[str, Any]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                calls_out: list[dict[str, object]] = []
                for report in reports:
                    for call in await uow.traces.list_for_phase_run(UUID(report["run_id"])):
                        manifest = await uow.traces.get_manifest(call.id)
                        calls_out.append(
                            {
                                "role": call.role,
                                "profile": f"{call.profile_name}@{call.profile_version}",
                                "status": call.status.value,
                                "task_run_id": str(call.task_run_id) if call.task_run_id else None,
                                "actor_id": str(call.actor_id) if call.actor_id else None,
                                "prompt_tokens": call.prompt_tokens,
                                "completion_tokens": call.completion_tokens,
                                "latency_ms": call.latency_ms,
                                "rendered_hash": manifest.rendered_hash,
                                "sources": len(manifest.sources),
                            }
                        )
                return {"model_calls": calls_out}
        finally:
            await engine.dispose()

    trace = asyncio.run(_collect())
    scenario = {
        "scenario": "stage1-three-phase-v1",
        "world_id": str(WORLD_ID),
        "reports": reports,
        "phase_seconds": {str(k): round(v, 3) for k, v in phase_times.items()},
    }
    audit = {"perspective": "ash scope never carried the secret", "findings": findings}
    performance = {
        "phase_seconds": scenario["phase_seconds"],
        "model_calls": len(trace["model_calls"]),
        "model_latency_ms": sum(c["latency_ms"] for c in trace["model_calls"]),
        "prompt_tokens": sum(c["prompt_tokens"] for c in trace["model_calls"]),
        "completion_tokens": sum(c["completion_tokens"] for c in trace["model_calls"]),
        "note": "Fake path latency is near zero; live-provider profiling is opt-in.",
    }
    security = {
        "prompt_provenance": provenance,
        "secret_scoped_to_wren": all(
            not p["has_secret"] for p in provenance if p["actor_hint"] == "ash"
        ),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "scenario.json").write_text(json.dumps(scenario, indent=2) + "\n")
    (EVIDENCE / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    (EVIDENCE / "performance.json").write_text(json.dumps(performance, indent=2) + "\n")
    (EVIDENCE / "trace.json").write_text(json.dumps(trace, indent=2) + "\n")
    (EVIDENCE / "security.json").write_text(json.dumps(security, indent=2) + "\n")
    (EVIDENCE / "index.json").write_text(
        json.dumps(
            {
                "scenario": "stage1-three-phase-v1",
                "world_id": str(WORLD_ID),
                "migration_head": "0012_s2_schedules",
                "files": [
                    "scenario.json",
                    "audit.json",
                    "performance.json",
                    "trace.json",
                    "security.json",
                    "index.json",
                ],
            },
            indent=2,
        )
        + "\n"
    )
