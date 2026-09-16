"""Seven-day orchestration: quiet suppression, quotas, recovery (owned by S2-ORCH-001)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest

from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.ids import new_character_id, new_location_id, new_world_id
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import (
    CHARACTER_FAKE_PROFILE,
    DIRECTOR_FAKE_PROFILE,
    NARRATOR_FAKE_PROFILE,
    REACTION_FAKE_PROFILE,
    RESOLVER_FAKE_PROFILE,
    SUMMARY_FAKE_PROFILE,
)
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings

PROFILES = {
    "character": CHARACTER_FAKE_PROFILE,
    "reaction": REACTION_FAKE_PROFILE,
    "resolver": RESOLVER_FAKE_PROFILE,
    "narrator": NARRATOR_FAKE_PROFILE,
    "director": DIRECTOR_FAKE_PROFILE,
    "summary": SUMMARY_FAKE_PROFILE,
}

PLACEHOLDER_SNAPSHOT = "00000000-0000-4000-8000-000000000000"


def _wait_json(actor: UUID) -> str:
    return json.dumps(
        {"family": "wait", "character_id": str(actor), "snapshot_id": PLACEHOLDER_SNAPSHOT}
    )


def _role_gateways(ids: dict[str, UUID], observe: bool = False) -> dict[str, FakeGateway]:
    def character_route(request: CompletionRequest) -> str | None:
        if "Wren" in request.prompt:
            if observe:
                return json.dumps(
                    {
                        "family": "observe",
                        "character_id": str(ids["wren"]),
                        "snapshot_id": PLACEHOLDER_SNAPSHOT,
                        "focus": "Ash",
                    }
                )
            return _wait_json(ids["wren"])
        if "Ash" in request.prompt:
            return _wait_json(ids["ash"])
        return None

    character = FakeGateway(profile=CHARACTER_FAKE_PROFILE, route=character_route)

    def reaction_route(request: CompletionRequest) -> str | None:
        if "Wren" in request.prompt:
            return _wait_json(ids["wren"])
        if "Ash" in request.prompt:
            return _wait_json(ids["ash"])
        return None

    reaction = FakeGateway(profile=REACTION_FAKE_PROFILE, route=reaction_route)
    resolver = FakeGateway(
        profile=RESOLVER_FAKE_PROFILE,
        default_text=json.dumps(
            {
                "outcome": "success",
                "effects": [],
                "rationale": "Nothing happens, calmly.",
            }
        ),
    )
    narrator = FakeGateway(
        profile=NARRATOR_FAKE_PROFILE,
        default_text=json.dumps(
            [{"text": "The phase passes.", "cited_fact_keys": ["attempt:wait"]}]
        ),
    )
    director = FakeGateway(
        profile=DIRECTOR_FAKE_PROFILE,
        default_text=json.dumps({"action": "noop", "reason": "calm stretch"}),
    )
    summary = FakeGateway(
        profile=SUMMARY_FAKE_PROFILE,
        default_text=json.dumps({"text": "The day passed quietly.", "source_ids": []}),
    )
    return {
        "character": character,
        "reaction": reaction,
        "resolver": resolver,
        "narrator": narrator,
        "director": director,
        "summary": summary,
    }


def _orchestrator(
    gateways: dict[str, FakeGateway],
    hook: Callable[[str], None] | None = None,
) -> Any:
    from worldsim.application.orchestration.stage1 import Stage1Orchestrator
    from worldsim.application.tasks.service import TaskService
    from worldsim.application.tracing.service import TraceService
    from worldsim.application.transactions.canonical import CanonicalTransaction
    from worldsim.infrastructure.tracing.langsmith import NullExporter

    engine = create_engine(Settings())
    factory = lambda: create_unit_of_work(engine)  # noqa: E731

    def _factory_role(role: str) -> FakeGateway:
        return gateways[role]

    return Stage1Orchestrator(
        factory,
        CanonicalTransaction(factory),
        TaskService(factory),
        TraceService(factory, NullExporter()),
        _factory_role,
        PROFILES,
        fault_hook=hook,
    )


async def _seed() -> dict[str, UUID]:
    from worldsim.domain.characters import Character, CharacterCard
    from worldsim.domain.ids import new_card_id

    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            await uow.worlds.add(World(id=wid, name="Orch", seed_version="s2-test"))
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
            return {"world": wid, "wren": wren, "ash": ash}
    finally:
        await engine.dispose()


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def test_quiet_phases_skip_narration_calls(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        orch = _orchestrator(gateways)
        reports = await orch.advance_days(ids["world"], 1, 1)
        assert len(reports) == 10
        assert all(r.quiet for r in reports)
        assert all(s.narration == "fallback" for r in reports for s in r.scenes)
        assert gateways["narrator"].calls == []
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                from worldsim.domain.time import absolute_index

                world = await uow.worlds.get(ids["world"])
                assert absolute_index(world.day, world.phase) == 10
                assert await uow.events.count_events(ids["world"]) >= 10
        finally:
            await engine.dispose()

    _run(_inner())


def test_quota_exhaustion_falls_back_without_losing_canon(
    migrated_db: None,
) -> None:
    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids, observe=True)
        orch = _orchestrator(gateways)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await uow.worlds.put_config(ids["world"], "model.max_calls_per_phase", 0)
                await uow.commit()
            reports = await orch.advance_days(ids["world"], 1, 1)
            assert len(reports) == 10
            assert all(s.narration == "fallback" for r in reports for s in r.scenes)
            assert gateways["narrator"].calls == []
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(ids["world"]) >= 10
        finally:
            await engine.dispose()

    _run(_inner())


def test_seven_days_survive_injected_failure(migrated_db: None) -> None:
    fired: list[str] = []

    def _hook(point: str) -> None:
        if point == "before_narration" and not fired:
            fired.append(point)
            raise RuntimeError("injected crash before narration")

    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        orch = _orchestrator(gateways, hook=_hook)
        engine = create_engine(Settings())
        try:
            with pytest.raises(RuntimeError, match="injected crash"):
                await orch.advance_days(ids["world"], 1, 7)
            assert fired == ["before_narration"]
            plain = _orchestrator(_role_gateways(ids))
            reports = await plain.advance_days(ids["world"], 1, 7)
            assert len(reports) == 70
            assert all(len(r.scenes) >= 1 for r in reports)
            async with create_unit_of_work(engine) as uow:
                from worldsim.domain.time import absolute_index

                world = await uow.worlds.get(ids["world"])
                assert (world.day, world.phase.value) == (8, "dawn")
                assert absolute_index(world.day, world.phase) == 70
                for report in reports:
                    run = await uow.phases.get_run(report.run_id)
                    assert run.state.value == "completed"
        finally:
            await engine.dispose()

    _run(_inner())


def test_quiet_party_still_narrates(migrated_db: None) -> None:
    """Suppression never starves model-authored combat and recruit tags."""
    from worldsim.domain.ids import new_party_member_id
    from worldsim.domain.party import PartyMember, party_name_key
    from worldsim.domain.rules.dnd import Sheet

    async def _inner() -> None:
        ids = await _seed()
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await uow.party.add(
                    PartyMember(
                        id=new_party_member_id(),
                        world_id=ids["world"],
                        name="Borin",
                        name_key=party_name_key("Borin"),
                        sheet=Sheet(
                            name="Borin",
                            race="dwarf",
                            character_class="fighter",
                            level=1,
                            stats={"str": 16, "dex": 12, "con": 15, "int": 8, "wis": 11, "cha": 10},
                            weapons=["longsword"],
                        ),
                    )
                )
                await uow.commit()
            gateways = _role_gateways(ids)
            orch = _orchestrator(gateways)
            reports = await orch.advance_days(ids["world"], 1, 1)
            assert all(r.quiet for r in reports)
            assert gateways["narrator"].calls != []
            assert all(s.narration == "narrated" for r in reports for s in r.scenes)
        finally:
            await engine.dispose()

    _run(_inner())
