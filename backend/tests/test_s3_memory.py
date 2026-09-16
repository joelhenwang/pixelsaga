"""Stage 3 memory lifecycle tests (owned by S3-MEM-001).

Salience scoring, citation bumps, midnight promotion, digest
retrieval, source immutability, and the promotion off-flag.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.application.orchestration.service import derive_run_id
from worldsim.domain.memory import (
    MAX_SALIENCE,
    MemoryDigest,
    content_hash,
    memory_hash,
    observation_hash,
    score_salience,
)
from worldsim.domain.perception import Observation, RecentMemory
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"

WORLD_ID = UUID("10000000-0000-4000-8000-000000000001")
WREN_ID = UUID("10000000-0000-4000-8000-000000000101")
ASH_ID = UUID("10000000-0000-4000-8000-000000000102")
PLACEHOLDER_SNAPSHOT = "00000000-0000-4000-8000-000000000000"
PROBE_TEXT = "the north bridge is cursed"


@pytest.fixture
def mem(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
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


def _cited_ids(prompt: str) -> list[str]:
    return sorted(
        set(f"{kind}:{raw}" for kind, raw in re.findall(r"(obs|mem):([0-9a-f-]{36})", prompt))
    )


def _route_for(probe_on_first: bool = False) -> Any:
    decide_calls = {"n": 0}

    def _route(request: Any) -> str | None:
        prompt, system = request.prompt, request.system or ""
        if "You decide" in system:
            if "Wren" in prompt:
                decide_calls["n"] += 1
                if probe_on_first and decide_calls["n"] == 1:
                    return json.dumps(
                        {
                            "family": "communicate",
                            "character_id": str(WREN_ID),
                            "snapshot_id": PLACEHOLDER_SNAPSHOT,
                            "target_character_id": str(ASH_ID),
                            "topic": PROBE_TEXT,
                        }
                    )
                return _wait_json(WREN_ID)
            return _wait_json(ASH_ID)
        if "You react" in system:
            return _wait_json(ASH_ID if "Ash" in prompt else WREN_ID)
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Quiet."})
        if "You distill" in system:
            ids = _cited_ids(prompt)
            return json.dumps({"text": f"Enduring: {len(ids)} older sources.", "source_ids": ids})
        if "You narrate" in system:
            return json.dumps([{"text": "The phase passes.", "cited_fact_keys": ["attempt:wait"]}])
        if "You direct" in system:
            return json.dumps({"action": "noop", "reason": "calm stretch"})
        if "You summar" in system:
            mem_ids = [i for i in _cited_ids(prompt) if i.startswith("mem:")]
            cited = mem_ids[:1]
            return json.dumps({"text": "A quiet day.", "source_ids": cited})
        return None

    return _route


def _advance(client: ApiClient, headers: dict[str, str], start: int, end: int) -> None:
    for index in range(start, end + 1):
        response = client.post(
            "/api/v1/stage1/advance",
            json={"world_id": str(WORLD_ID), "absolute_index": index},
            headers=headers,
        )
        assert response.status_code == 200, response.text


def test_salience_scoring_math() -> None:
    assert score_salience(2.0, 0, 40) == 2.0
    assert score_salience(2.0, 40, 40) == pytest.approx(1.0)
    assert score_salience(2.0, 80, 40) == pytest.approx(0.5)
    assert score_salience(1.0, 10**6, 40) == pytest.approx(0.0, abs=1e-6)


def test_content_hashes_stable() -> None:
    facts = [{"key": "road", "value": "quiet"}]
    assert observation_hash(facts) == observation_hash(list(facts))
    assert memory_hash("hello") == content_hash("hello")
    assert len(observation_hash(facts)) == 64


def test_summary_citation_bumps_salience(mem: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = mem
    gateway.route = _route_for()
    headers = {"X-Worldsim-Role": "watcher"}
    client.post("/api/v1/world/seed", headers=headers)
    _advance(client, headers, 1, 10)

    async def _audit() -> tuple[float, float]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                memories = await uow.perception.memories_for_owner(WREN_ID)
                bumped = [m for m in memories if m.salience > 1.0]
                assert bumped, "fake summary cites first memory daily"
                assert all(m.salience <= MAX_SALIENCE for m in memories)
                cited = bumped[0]
                assert cited.content_hash == memory_hash(cited.text)
                return cited.salience, max(m.salience for m in memories)
        finally:
            await engine.dispose()

    first, highest = asyncio.run(_audit())
    assert first == 2.0
    assert highest == 2.0


def test_promotion_digests_old_salient_sources(
    mem: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = mem
    gateway.route = _route_for(probe_on_first=True)
    headers = {"X-Worldsim-Role": "watcher"}
    client.post("/api/v1/world/seed", headers=headers)
    _advance(client, headers, 1, 20)

    async def _audit() -> list[MemoryDigest]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                return await uow.digests.list_for_owner(WORLD_ID, WREN_ID)
        finally:
            await engine.dispose()

    digests = asyncio.run(_audit())
    assert len(digests) == 1
    digest = digests[0]
    assert digest.day == 2
    assert digest.prompt_version == "digest.v1"
    assert any(s.startswith("mem:") for s in digest.source_ids)

    async def _sources_intact() -> bool:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                memories: dict[str, RecentMemory] = {
                    str(m.id): m for m in await uow.perception.memories_for_owner(WREN_ID)
                }
                observations: dict[str, Observation] = {}
                for obs in await uow.perception.observations_for_observer(WREN_ID, 100000):
                    observations[str(obs.id)] = obs
                for source in digest.source_ids:
                    kind, _, raw = source.partition(":")
                    if kind == "mem":
                        row = memories.get(raw)
                        assert row is not None
                        assert row.content_hash == memory_hash(row.text)
                    elif kind == "obs":
                        row = observations.get(raw)
                        assert row is not None
                        assert row.content_hash == observation_hash(
                            [{"key": f.key, "value": f.value} for f in row.facts]
                        )
                return True
        finally:
            await engine.dispose()

    assert asyncio.run(_sources_intact())


def test_digest_reenters_assembly_with_fixed_score(
    mem: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = mem
    gateway.route = _route_for(probe_on_first=True)
    headers = {"X-Worldsim-Role": "watcher"}
    client.post("/api/v1/world/seed", headers=headers)
    _advance(client, headers, 1, 25)

    async def _audit() -> dict[str, int]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                digests = await uow.digests.list_for_owner(WORLD_ID, WREN_ID)
                assert digests, "promotion must have produced a digest by day 2"
                wanted = {f"digest:{d.id}" for d in digests}
                reasons: dict[str, int] = {}
                run = await uow.phases.get_run(derive_run_id(WORLD_ID, 25))
                for call in await uow.traces.list_for_phase_run(run.id):
                    try:
                        manifest = await uow.traces.get_manifest(call.id)
                    except Exception:  # calls without manifests
                        continue
                    for source in manifest.sources:
                        if source.source_id in wanted:
                            reasons[source.reason] = reasons.get(source.reason, 0) + 1
                return reasons
        finally:
            await engine.dispose()

    reasons = asyncio.run(_audit())
    assert reasons.get("permitted"), reasons


def test_promotion_off_flag_disables_digests(
    mem: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = mem
    gateway.route = _route_for(probe_on_first=True)
    headers = {"X-Worldsim-Role": "watcher"}
    client.post("/api/v1/world/seed", headers=headers)

    async def _disable() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await uow.worlds.put_config(WORLD_ID, "memory.promotion.enabled", False)
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(_disable())
    _advance(client, headers, 1, 20)

    async def _audit() -> int:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                digests = await uow.digests.list_for_owner(WORLD_ID, WREN_ID)
                return len(digests)
        finally:
            await engine.dispose()

    assert asyncio.run(_audit()) == 0


def test_perception_repo_stays_append_only() -> None:
    from worldsim.infrastructure.repositories.perception import (
        SqlAlchemyPerceptionRepository,
    )

    surface = set(dir(SqlAlchemyPerceptionRepository))
    assert any(name.startswith("update") or name.startswith("delete") for name in surface) is False
    assert "save" not in surface
