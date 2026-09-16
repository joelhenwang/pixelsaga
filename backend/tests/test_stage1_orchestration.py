"""Three-phase autonomous orchestration checks (owned by S1-ORCH-001)."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest

from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
from worldsim.application.orchestration.stage1 import Stage1Orchestrator
from worldsim.application.ports.model_gateway import CompletionRequest, ProbeResult
from worldsim.application.tasks.service import TaskService
from worldsim.application.tracing.service import TraceService
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.commands import CommunicateAction
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    derive_intent_id,
    new_card_id,
    new_character_id,
    new_location_id,
    new_world_id,
)
from worldsim.domain.phases import PhaseRun
from worldsim.domain.time import absolute_index
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import (
    CHARACTER_FAKE_PROFILE,
    DIRECTOR_FAKE_PROFILE,
    NARRATOR_FAKE_PROFILE,
    REACTION_FAKE_PROFILE,
    RESOLVER_FAKE_PROFILE,
)
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.tracing.langsmith import NullExporter

PROFILES = {
    "character": CHARACTER_FAKE_PROFILE,
    "reaction": REACTION_FAKE_PROFILE,
    "resolver": RESOLVER_FAKE_PROFILE,
    "narrator": NARRATOR_FAKE_PROFILE,
    "director": DIRECTOR_FAKE_PROFILE,
}


async def _seed() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            await uow.worlds.add(World(id=wid, name="Orch", seed_version="s1-test"))
            hearth, market = new_location_id(), new_location_id()
            await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth"))
            await uow.locations.add(Location(id=market, world_id=wid, name="Market"))
            wren, ash = new_character_id(), new_character_id()
            for cid, name, place in ((wren, "Wren", hearth), (ash, "Ash", market)):
                await uow.characters.add_identity(cid, wid, name)
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=cid, name=name, version=1)
                )
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=wid,
                        name=name,
                        card_version=1,
                        location_id=place,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
            await uow.versions.ensure(wid, wid, "world")
            await uow.commit()
            return {"world": wid, "wren": wren, "ash": ash, "hearth": hearth, "market": market}
    finally:
        await engine.dispose()


def _wait_json(actor: UUID, snapshot: UUID) -> str:
    return json.dumps({"family": "wait", "character_id": str(actor), "snapshot_id": str(snapshot)})


def _beats_json() -> str:
    return json.dumps([{"text": "The phase passes.", "cited_fact_keys": ["attempt:wait"]}])


def _role_gateways(
    ids: dict[str, UUID], narrator_text: str | None = None
) -> dict[str, FakeGateway]:
    snapshot_cache: dict[int, UUID] = {}

    def snapshot_for(index: int) -> UUID:
        if index not in snapshot_cache:
            snapshot_cache[index] = derive_snapshot_id(derive_run_id(ids["world"], index))
        return snapshot_cache[index]

    def character_route(request: CompletionRequest) -> str | None:
        for index in (1, 2, 3):
            snapshot = snapshot_for(index)
            if "Wren" in request.prompt:
                return _wait_json(ids["wren"], snapshot)
            if "Ash" in request.prompt:
                return _wait_json(ids["ash"], snapshot)
        return None

    def reaction_route(request: CompletionRequest) -> str | None:
        for index in (1, 2, 3):
            snapshot = snapshot_for(index)
            if "Wren" in request.prompt:
                return json.dumps(
                    {
                        "family": "observe",
                        "character_id": str(ids["wren"]),
                        "snapshot_id": str(snapshot),
                        "focus": "Ash",
                    }
                )
            if "Ash" in request.prompt:
                return _wait_json(ids["ash"], snapshot)
        return None

    character = FakeGateway(profile=CHARACTER_FAKE_PROFILE, route=character_route)
    reaction = FakeGateway(profile=REACTION_FAKE_PROFILE, route=reaction_route)
    resolver = FakeGateway(
        profile=RESOLVER_FAKE_PROFILE,
        default_text=json.dumps(
            {
                "outcome": "success",
                "effects": [
                    {
                        "schema_version": 1,
                        "affected_ids": [str(ids["wren"])],
                        "expected_versions": {str(ids["wren"]): 0},
                        "effect_type": "record_observation",
                        "observer_character_id": str(ids["wren"]),
                        "facts": [{"key": "greeting", "value": "dawn patrol"}],
                    }
                ],
                "rationale": "Wren hears the patrol call.",
            }
        ),
    )
    narrator = FakeGateway(
        profile=NARRATOR_FAKE_PROFILE, default_text=narrator_text or _beats_json()
    )
    director = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
    return {
        "character": character,
        "reaction": reaction,
        "resolver": resolver,
        "narrator": narrator,
        "director": director,
    }


def _orchestrator(
    gateways: dict[str, FakeGateway],
    hook: Callable[[str], None] | None = None,
) -> Stage1Orchestrator:
    engine = create_engine(Settings())
    factory = lambda: create_unit_of_work(engine)  # noqa: E731

    def _factory_role(role: str) -> FakeGateway:
        return gateways[role]

    return Stage1Orchestrator(
        factory,
        CanonicalTransaction(factory, pre_commit_hook=hook),
        TaskService(factory),
        TraceService(factory, NullExporter()),
        _factory_role,
        PROFILES,
        fault_hook=hook,
    )


def test_three_phases_complete_with_shared_snapshots(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        orch = _orchestrator(_role_gateways(ids))
        reports = await orch.advance_three_phases(ids["world"], 1)
        assert len(reports) == 3
        for report in reports:
            assert not report.duplicate
            assert len(report.scenes) >= 1
            assert all(s.narration in ("narrated", "fallback") for s in report.scenes)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                world = await uow.worlds.get(ids["world"])
                assert absolute_index(world.day, world.phase) == 3
                assert await uow.events.count_events(ids["world"]) >= 6
                run = await uow.phases.get_run(reports[0].run_id)
                assert run.state.value == "completed"
                snapshot = await uow.phases.get_snapshot(reports[1].snapshot_id)
                assert len(snapshot.characters) == 2
                calls = await uow.traces.list_for_phase_run(reports[2].run_id)
                assert len(calls) >= 2
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_duplicate_phase_replays_without_new_canon(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        orch = _orchestrator(_role_gateways(ids))
        first = await orch.advance_phase(ids["world"], 1)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                before = await uow.events.count_events(ids["world"])
            second = await orch.advance_phase(ids["world"], 1)
            assert second.duplicate
            assert [s.event_id for s in second.scenes] == [s.event_id for s in first.scenes]
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(ids["world"]) == before
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_restart_during_commit_resolves_once(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        fired: list[str] = []

        def _hook(point: str) -> None:
            if point == "after_scene" and not fired:
                fired.append(point)
                raise RuntimeError("injected at after_scene")

        orch = _orchestrator(gateways, hook=_hook)
        with pytest.raises(RuntimeError, match="injected"):
            await orch.advance_phase(ids["world"], 1)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                mid = await uow.events.count_events(ids["world"])
            assert mid >= 1
            orch = _orchestrator(gateways)
            report = await orch.advance_phase(ids["world"], 1)
            assert not report.duplicate
            async with create_unit_of_work(engine) as uow:
                after = await uow.events.count_events(ids["world"])
                # One tick plus one event per committed scene, never doubled.
                assert after == mid + len(report.scenes)
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_restart_before_narration_heals(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        fired: list[str] = []

        def _hook(point: str) -> None:
            if point == "before_narration" and not fired:
                fired.append(point)
                raise RuntimeError("injected at before_narration")

        orch = _orchestrator(gateways, hook=_hook)
        with pytest.raises(RuntimeError, match="injected"):
            await orch.advance_phase(ids["world"], 1)
        orch = _orchestrator(gateways)
        report = await orch.advance_phase(ids["world"], 1)
        assert all(s.narration in ("narrated", "fallback") for s in report.scenes)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                for scene in report.scenes:
                    assert await uow.scenes.narrations_for_event(scene.event_id)
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_player_substitution_controls_attempt(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)

        def _ash_only(request: CompletionRequest) -> str | None:
            if "Ash" in request.prompt:
                raise AssertionError("Ash is player-controlled; no model call expected")
            if "Wren" in request.prompt:
                snapshot = derive_snapshot_id(derive_run_id(ids["world"], 1))
                return _wait_json(ids["wren"], snapshot)
            return None

        gateways["character"].route = _ash_only
        orch = _orchestrator(gateways)
        player = {
            ids["ash"]: CommunicateAction(
                character_id=ids["ash"],
                snapshot_id=derive_snapshot_id(derive_run_id(ids["world"], 1)),
                target_character_id=ids["wren"],
                topic="dawn patrol",
            )
        }
        report = await orch.advance_phase(ids["world"], 1, player)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                intent = await uow.scenes.get_intent(
                    derive_intent_id(
                        ids["world"],
                        report.snapshot_id,
                        ids["ash"],
                    )
                )
                assert intent.action.family.value == "communicate"
                assert intent.action.topic == "dawn patrol"  # type: ignore[union-attr]
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_pause_blocks_until_resume(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        orch = _orchestrator(_role_gateways(ids))
        run_id = derive_run_id(ids["world"], 1)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await uow.phases.create_run(
                    PhaseRun(id=run_id, world_id=ids["world"], absolute_index=1)
                )
                await uow.commit()
        finally:
            await engine.dispose()
        await orch.pause_phase(run_id)
        with pytest.raises(DomainError) as excinfo:
            await orch.advance_phase(ids["world"], 1)
        assert excinfo.value.code is ErrorCode.PRECONDITION_FAILED
        await orch.resume_phase(run_id)
        report = await orch.advance_phase(ids["world"], 1)
        assert not report.duplicate

    asyncio.run(_inner())


class _DeadGateway:
    profile = CHARACTER_FAKE_PROFILE

    async def complete(self, request: CompletionRequest) -> Any:
        raise AssertionError("must not be called")

    async def probe(self) -> ProbeResult:
        return ProbeResult(ok=False, profile="dead", latency_ms=0, detail="quota exhausted")

    async def embed(self, request: Any) -> Any:
        raise AssertionError("must not be called")


def test_probe_gate_blocks_batch_before_commit(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        dead = _DeadGateway()

        def _gateway_for(role: str) -> FakeGateway | _DeadGateway:
            return dead if role == "character" else gateways[role]

        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            orch = Stage1Orchestrator(
                factory,
                CanonicalTransaction(factory),
                TaskService(factory),
                TraceService(factory, NullExporter()),
                _gateway_for,
                PROFILES,
            )
            with pytest.raises(DomainError) as excinfo:
                await orch.advance_phase(ids["world"], 1)
            assert excinfo.value.code is ErrorCode.PRECONDITION_FAILED
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(ids["world"]) == 0
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_narration_failure_completes_phase(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        from worldsim.application.ports.model_gateway import ModelUnavailableError

        gateways["narrator"].enqueue_error(ModelUnavailableError("provider down"))
        gateways["narrator"].enqueue_error(ModelUnavailableError("provider down"))
        # Default text would mask the outage; clear it for this phase.
        gateways["narrator"].default_text = None
        orch = _orchestrator(gateways)
        report = await orch.advance_phase(ids["world"], 1)
        assert not report.duplicate
        assert all(s.narration == "fallback" for s in report.scenes)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(ids["world"]) >= 2
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_derived_ids_converge() -> None:
    world, snapshot, author = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    first = derive_intent_id(world, snapshot, author)
    assert derive_intent_id(world, snapshot, author) == first
    assert derive_intent_id(world, snapshot, uuid.uuid4()) != first
