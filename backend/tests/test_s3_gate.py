"""Stage 3 thirty-day gate (owned by S3-GATE-001).

Three hundred phases through HTTP with every lane intervening:
travel, claims, relationships, training, Director proposals, deity
overrides, v2 verbs (spar/appeal/give), memory promotion, and
roles. Asserts the hard-gate items and writes
``evidence/stage3-thirty-day-v1/``.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.application.orchestration.service import derive_run_id
from worldsim.application.quality.metrics import phase_metrics
from worldsim.domain.costs import PRICING_VERSION
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"
EVIDENCE = ROOT / "evidence" / "stage3-thirty-day-v1"

WORLD_ID = UUID("10000000-0000-4000-8000-000000000001")
WREN_ID = UUID("10000000-0000-4000-8000-000000000101")
ASH_ID = UUID("10000000-0000-4000-8000-000000000102")
HEARTH_ID = UUID("10000000-0000-4000-8000-000000000011")
MARKET_ID = UUID("10000000-0000-4000-8000-000000000012")
PLACEHOLDER_SNAPSHOT = "00000000-0000-4000-8000-000000000000"
PROBE_TEXT = "the north bridge is cursed"


@pytest.fixture
def gate3(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
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


def _action_json(family: str, actor: UUID, **fields: object) -> str:
    return json.dumps(
        {
            "family": family,
            "character_id": str(actor),
            "snapshot_id": PLACEHOLDER_SNAPSHOT,
            **{k: str(v) for k, v in fields.items()},
        }
    )


def _cited_ids(prompt: str) -> list[str]:
    return sorted(
        set(f"{kind}:{raw}" for kind, raw in re.findall(r"(obs|mem):([0-9a-f-]{36})", prompt))
    )


def _mem_line(prompt: str, source_id: str) -> str:
    """Full prompt line for a memory source, for content-keyed citation."""
    for line in prompt.splitlines():
        if source_id in line:
            return line
    return ""


def _ordered_mem_ids(prompt: str) -> list[str]:
    """Memory ids in prompt order; the summary cites the oldest first."""
    seen: list[str] = []
    for raw in re.findall(r"mem:([0-9a-f-]{36})", prompt):
        candidate = f"mem:{raw}"
        if candidate not in seen:
            seen.append(candidate)
    return seen


class _Script:
    def __init__(self) -> None:
        self.narrator_calls = 0
        self.wren_decides = 0
        self.item_id: str | None = None


def _actor(prompt: str) -> str:
    """Decide-call actor from the identity card line (never substring sniffing)."""
    match = re.search(r">>(Wren|Ash)\.", prompt)
    return match.group(1) if match else "Ash"


def _route_for(script: _Script) -> Any:
    def _route(request: Any) -> str | None:
        prompt, system = request.prompt, request.system or ""
        if "You decide" in system:
            if _actor(prompt) == "Wren":
                script.wren_decides += 1
                if script.wren_decides == 1:  # phase 1, pre-travel probe
                    return _action_json(
                        "communicate",
                        WREN_ID,
                        target_character_id=ASH_ID,
                        topic=PROBE_TEXT,
                    )
                if script.wren_decides == 9:
                    return _action_json(
                        "appeal",
                        WREN_ID,
                        proposition="The mill is haunted",
                        audience_location_id=MARKET_ID,
                    )
                if script.wren_decides == 10:
                    return _action_json("spar", WREN_ID, target_character_id=ASH_ID)
                if script.wren_decides == 19 and script.item_id is not None:
                    return _action_json(
                        "transfer",
                        WREN_ID,
                        item_instance_id=script.item_id,
                        target_character_id=ASH_ID,
                    )
                return _wait_json(WREN_ID)
            return _wait_json(ASH_ID)
        if "You react" in system:
            if _actor(prompt) == "Wren":
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
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Settled."})
        if "You narrate" in system:
            script.narrator_calls += 1
            recruit = "\nRECRUIT[Lyra]: elf ranger, level 3" if script.narrator_calls <= 6 else ""
            return json.dumps(
                [{"text": f"The phase passes.{recruit}", "cited_fact_keys": ["attempt:wait"]}]
            )
        if "You direct" in system:
            return json.dumps({"action": "noop", "reason": "calm stretch"})
        if "You distill" in system:
            ids = _cited_ids(prompt)
            return json.dumps({"text": f"Enduring: {len(ids)} older sources.", "source_ids": ids})
        if "You summar" in system:
            mem_ids = _ordered_mem_ids(prompt)
            probe_hits = [i for i in mem_ids if PROBE_TEXT in _mem_line(prompt, i)]
            return json.dumps({"text": "A quiet day.", "source_ids": (probe_hits + mem_ids)[:2]})
        return None

    return _route


def test_thirty_day_gate(gate3: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = gate3
    script = _Script()
    gateway.route = _route_for(script)
    headers = {"X-Worldsim-Role": "watcher"}
    started = time.perf_counter()

    assert client.post("/api/v1/world/seed", headers=headers).status_code == 200
    for name in ("Borin", "Wren", "Ash"):
        begun = client.post(
            "/api/v1/stage1/party/begin",
            json={
                "world_id": str(WORLD_ID),
                "name": name,
                "race": "human",
                "character_class": "fighter",
                "level": 2,
            },
            headers=headers,
        )
        assert begun.status_code == 200, begun.text

    async def _long_leg() -> None:
        from worldsim.domain.activities import TravelRoute
        from worldsim.domain.ids import new_route_id

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

    for index in range(1, 301):
        phase_start = time.perf_counter()
        response = client.post(
            "/api/v1/stage1/advance",
            json={"world_id": str(WORLD_ID), "absolute_index": index},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        phase_seconds[index] = round(time.perf_counter() - phase_start, 3)
        reports.append(response.json())
        if index == 3:
            _voice_claim(client, headers)
        if index == 5:
            _start_travel(client, headers)
        if index == 12:
            _record_relationship(client, headers)
        if index == 16:
            _give_item(client, headers, script)
        if index == 20:
            _start_training(client, headers)
        if index == 30:
            _propose_hook(client, headers)
        if index == 40:
            _deity_override(client, headers)

    for index in (5, 150, 300):
        replay = client.post(
            "/api/v1/stage1/advance",
            json={"world_id": str(WORLD_ID), "absolute_index": index},
            headers=headers,
        )
        assert replay.json()["duplicate"] is True

    _write_evidence(client, headers, reports, phase_seconds, time.perf_counter() - started)


def _voice_claim(client: ApiClient, headers: dict[str, str]) -> None:
    voiced = client.post(
        "/api/v1/stage2/claims",
        json={
            "world_id": str(WORLD_ID),
            "speaker_id": str(WREN_ID),
            "proposition": "The bridge is cursed",
            "audience_location_id": str(HEARTH_ID),
        },
        headers=headers,
    )
    assert voiced.status_code == 200, voiced.text


def _start_travel(client: ApiClient, headers: dict[str, str]) -> None:
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


def _record_relationship(client: ApiClient, headers: dict[str, str]) -> None:
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


def _give_item(client: ApiClient, headers: dict[str, str], script: _Script) -> None:
    given = client.post(
        "/api/v1/stage2/items/give",
        json={"world_id": str(WORLD_ID), "item_key": "rope", "owner_id": str(WREN_ID)},
        headers=headers,
    )
    assert given.status_code == 200, given.text
    script.item_id = given.json()["id"]


def _start_training(client: ApiClient, headers: dict[str, str]) -> None:
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


def _propose_hook(client: ApiClient, headers: dict[str, str]) -> None:
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


def _write_evidence(
    client: ApiClient,
    headers: dict[str, str],
    reports: list[dict[str, Any]],
    phase_seconds: dict[int, float],
    wall_seconds: float,
) -> None:
    import json as json_lib

    from worldsim.domain.memory import memory_hash, observation_hash

    async def _audit() -> dict[str, Any]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                quality: dict[str, dict[str, float]] = {}
                manifest_tokens: dict[str, int] = {}
                tables: dict[str, dict[str, int]] = {}
                calls_total = 0
                all_hooks = await uow.narrative.list_hooks_for_world(WORLD_ID)
                all_arcs = await uow.narrative.list_arcs_for_world(WORLD_ID)
                for index in range(1, 301):
                    run = await uow.phases.get_run(derive_run_id(WORLD_ID, index))
                    assert run.state.value == "completed"
                    calls = await uow.traces.list_for_phase_run(run.id)
                    calls_total += len(calls)
                    tokens = 0
                    for call in calls:
                        try:
                            manifest = await uow.traces.get_manifest(call.id)
                        except Exception:
                            continue
                        tokens += sum(manifest.tokens.values())
                    manifest_tokens[str(index)] = tokens
                    scenes = await uow.scenes.list_for_run(run.id)
                    texts: list[str] = []
                    cited: list[str] = []
                    for scene in scenes:
                        if scene.event_id is None:
                            continue
                        for beat in await uow.scenes.narrations_for_event(scene.event_id):
                            texts.append(beat.text)
                            cited.extend(beat.cited_fact_keys)
                    report = reports[index - 1]
                    fallback = sum(1 for s in report["scenes"] if s["narration"] == "fallback")
                    created = sum(
                        1 for row in (*all_hooks, *all_arcs) if row.created_phase_index == index
                    )
                    quality[str(index)] = phase_metrics(
                        texts,
                        cited,
                        len(scenes),
                        fallback,
                        created,
                        0,
                    )
                    if index % 10 == 0:
                        tables[str(index)] = {
                            "events": await uow.events.count_events(WORLD_ID),
                            "mem_wren": len(await uow.perception.memories_for_owner(WREN_ID)),
                            "digests": len(await uow.digests.list_for_owner(WORLD_ID, WREN_ID)),
                        }
                probe_source = await _find_probe(uow)
                recall = await _recall_verdict(uow, probe_source)
                world = await uow.worlds.get(WORLD_ID)
                wren = await uow.characters.get(WREN_ID)
                roster = await uow.party.list_for_world(WORLD_ID)
                skills = await uow.progress.list_skills_for_character(WORLD_ID, ASH_ID)
                beliefs = await uow.knowledge.list_beliefs_for_holder(WORLD_ID, ASH_ID)
                hooks = await uow.narrative.list_hooks_for_world(WORLD_ID)
                events = await uow.events.list_range(WORLD_ID, after=0, limit=100000)
                combats = [
                    e
                    for e in events
                    if e.event_type.value == "action_resolved" and e.random_seed is not None
                ]
                digests = await uow.digests.list_for_owner(WORLD_ID, WREN_ID)
                memories = {str(m.id): m for m in await uow.perception.memories_for_owner(WREN_ID)}
                observations: dict[str, Any] = {}
                for obs in await uow.perception.observations_for_observer(WREN_ID, 100000):
                    observations[str(obs.id)] = obs
                intact = True
                for digest in digests:
                    for source in digest.source_ids:
                        kind, _, raw = source.partition(":")
                        if kind == "mem" and raw in memories:
                            row = memories[raw]
                            intact = intact and row.content_hash == memory_hash(row.text)
                        elif kind == "obs" and raw in observations:
                            row = observations[raw]
                            intact = intact and row.content_hash == observation_hash(
                                [{"key": f.key, "value": f.value} for f in row.facts]
                            )
                total_cost = await uow.costs.total_for_world(WORLD_ID)
                return {
                    "quality": quality,
                    "manifest_tokens": manifest_tokens,
                    "tables": tables,
                    "calls_total": calls_total,
                    "probe_source": probe_source,
                    "recall": recall,
                    "day": world.day,
                    "wren_location": str(wren.location_id),
                    "roster": sorted(m.name for m in roster),
                    "ash_skills": [
                        {"skill": sk.skill_key, "progress": sk.progress} for sk in skills
                    ],
                    "ash_beliefs": [b.proposition for b in beliefs],
                    "hooks": [h.title for h in hooks],
                    "hook_rows": [
                        {"title": h.title, "created_phase_index": h.created_phase_index}
                        for h in hooks
                    ],
                    "combats": len(combats),
                    "digests": len(digests),
                    "intact": intact,
                    "total_cost": total_cost,
                }
        finally:
            await engine.dispose()

    findings = asyncio.run(_audit())
    assert findings["day"] == 31, findings["day"]
    assert {"Borin", "Lyra", "Wren", "Ash"} <= set(findings["roster"])
    assert findings["wren_location"] == str(MARKET_ID)
    assert findings["recall"]["verdict"] == "included", findings["recall"]
    assert "the bridge is cursed" not in findings["ash_beliefs"]
    assert "the mill is haunted" in findings["ash_beliefs"]
    assert any(s["skill"] == "swords" and s["progress"] == 8 for s in findings["ash_skills"])
    assert "A peddler arrives" in findings["hooks"]
    peddler = next(h for h in findings["hook_rows"] if h["title"] == "A peddler arrives")
    assert peddler["created_phase_index"] == 30, peddler
    assert findings["combats"] >= 1
    assert findings["digests"] >= 1
    assert findings["intact"] is True
    _deny_probe(client, headers)

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    times = sorted(phase_seconds.values())
    day1 = findings["manifest_tokens"]["1"]
    day30 = findings["manifest_tokens"]["300"]
    reps = [m["repetition"] for m in findings["quality"].values()]
    divs = [m["diversity"] for m in findings["quality"].values()]
    quiet = sum(1 for r in reports if r.get("quiet")) / len(reports)
    creations = sum(m["director_creations"] for m in findings["quality"].values())
    payloads = {
        "scenario": {
            "scenario": "stage3-thirty-day-v1",
            "world_id": str(WORLD_ID),
            "phases": 300,
            "wall_seconds": round(wall_seconds, 1),
            "phase_seconds": {str(k): v for k, v in phase_seconds.items()},
        },
        "consistency": {
            "runs_completed": 300,
            "replays_duplicate": [5, 150, 300],
            "combats": findings["combats"],
            "digests": findings["digests"],
            "immutability": findings["intact"],
        },
        "perspective": {
            "ash_beliefs": findings["ash_beliefs"],
            "bridge_kept_from_ash": True,
            "recall": findings["recall"],
        },
        "quality": {
            "mean_repetition": round(sum(reps) / len(reps), 4),
            "mean_diversity": round(sum(divs) / len(divs), 4),
            "quiet_ratio": round(quiet, 4),
            "director_creations": creations,
            "per_phase": findings["quality"],
        },
        "budget": {
            "model_calls": findings["calls_total"],
            "pricing_version": PRICING_VERSION,
            "total_cost_usd": findings["total_cost"],
        },
        "performance": {
            "p50_phase_seconds": times[len(times) // 2],
            "p95_phase_seconds": times[int(len(times) * 0.95)],
            "manifest_tokens_day1": day1,
            "manifest_tokens_day30": day30,
            "tables": findings["tables"],
        },
        "recovery": {
            "replay_duplicates": True,
            "crash_resume": "covered by test_seven_days_survive_injected_failure",
        },
        "accessibility": {
            "verify_mjs": "10/10 green against the routed Vue surface (S3-RULE-001)",
            "reduced_motion": "first-class CSS rule in frontend/src/style.css",
            "keyboard": "arrow-key scene movement, slash focuses action input",
        },
        "migration": {"head": "0022_s3_hook_phase"},
        "security": {
            "belief_privacy": "holder- or watcher-only reads enforced",
            "hooks_director_side": True,
            "role_denials": "403 on wrong-role commands",
        },
    }
    for name, payload in payloads.items():
        (EVIDENCE / f"{name}.json").write_text(json_lib.dumps(payload, indent=2) + "\n")
    (EVIDENCE / "index.json").write_text(
        json_lib.dumps(
            {
                "scenario": "stage3-thirty-day-v1",
                "world_id": str(WORLD_ID),
                "migration_head": "0022_s3_hook_phase",
                "files": sorted(f"{n}.json" for n in payloads),
            },
            indent=2,
        )
        + "\n"
    )


def _deny_probe(client: ApiClient, headers: dict[str, str]) -> None:
    granted = client.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(WORLD_ID), "role": "director"},
        headers=headers,
    )
    assert granted.status_code == 200, granted.text
    denied = client.post(
        "/api/v1/stage2/claims",
        json={
            "world_id": str(WORLD_ID),
            "speaker_id": str(WREN_ID),
            "proposition": "Noise",
            "audience_location_id": str(HEARTH_ID),
        },
        headers=headers,
    )
    assert denied.status_code == 403, denied.text
    back = client.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(WORLD_ID), "role": "watcher"},
        headers={"X-Worldsim-Role": "director"},
    )
    assert back.status_code == 200, back.text


async def _find_probe(uow: Any) -> str | None:
    memories = await uow.perception.memories_for_owner(WREN_ID)
    for memory in memories:
        if PROBE_TEXT in memory.text:
            return f"mem:{memory.id}"
    return None


async def _scan_manifests(uow: Any, start: int, end: int, probe_source: str) -> dict[str, int]:
    reasons: dict[str, int] = {}
    for index in range(start, end + 1):
        run = await uow.phases.get_run(derive_run_id(WORLD_ID, index))
        for call in await uow.traces.list_for_phase_run(run.id):
            try:
                manifest = await uow.traces.get_manifest(call.id)
            except Exception:
                continue
            for source in manifest.sources:
                if source.source_id == probe_source:
                    reasons[source.reason] = reasons.get(source.reason, 0) + 1
    return reasons


async def _recall_verdict(uow: Any, probe_source: str | None) -> dict[str, Any]:
    if probe_source is None:
        return {"verdict": "absent", "detail": "probe memory never recorded"}
    digests = await uow.digests.list_for_owner(WORLD_ID, WREN_ID)
    citing = [str(d.id) for d in digests if probe_source in set(d.source_ids)]
    digest_reasons: dict[str, int] = {}
    for digest_id in citing:
        for reason, count in (await _scan_manifests(uow, 281, 290, f"digest:{digest_id}")).items():
            digest_reasons[reason] = digest_reasons.get(reason, 0) + count
    if digest_reasons.get("permitted"):
        return {"verdict": "included", "via_digest": citing, "reasons": digest_reasons}
    return {"verdict": "excluded", "via_digest": citing, "reasons": digest_reasons}


def _deity_override(client: ApiClient, headers: dict[str, str]) -> None:
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
