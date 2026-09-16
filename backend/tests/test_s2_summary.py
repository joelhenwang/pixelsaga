"""Daily summaries: perspective, provenance, safe fallback (owned by S2-SUMMARY-001)."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID, uuid4

from worldsim.application.graphs.state import GraphInvocation
from worldsim.application.graphs.summary import (
    SUMMARY_PROMPT_VERSION,
    SummaryGraphDeps,
    build_summary_graph,
    load_summary_prompt,
)
from worldsim.application.ports.model_gateway import ModelUnavailableError
from worldsim.domain.characters import Character
from worldsim.domain.enums import EventType
from worldsim.domain.events import WorldEvent
from worldsim.domain.ids import (
    new_character_id,
    new_location_id,
    new_phase_run_id,
    new_task_id,
    new_world_id,
)
from worldsim.domain.perception import Observation, ObservationFact
from worldsim.domain.phases import PhaseRun
from worldsim.domain.summaries import day_range, fallback_text
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import SUMMARY_FAKE_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def _graph(gateway: FakeGateway) -> Any:
    return build_summary_graph(
        SummaryGraphDeps(
            gateway=gateway,
            profile=SUMMARY_FAKE_PROFILE,
            system_template=load_summary_prompt(),
        )
    )


def _invocation(owner: str, sources: list[str]) -> GraphInvocation:
    return GraphInvocation(
        graph_name="daily-summary",
        graph_version="v1",
        task_run_id=new_task_id(),
        world_id=new_world_id(),
        phase_run_id=new_phase_run_id(),
        snapshot_id=new_task_id(),
        role="daily_summary",
        profile_version=SUMMARY_FAKE_PROFILE.version,
        prompt_version=SUMMARY_PROMPT_VERSION,
        input={
            "owner_name": owner,
            "day": 1,
            "sources_text": "\n".join(sources),
            "source_ids": [s.split(" ")[0] for s in sources],
        },
    )


def test_graph_proposes_cited_retelling() -> None:
    text = json.dumps({"text": "Wren watched the road.", "source_ids": ["obs:1"]})

    async def _inner() -> None:
        from worldsim.application.graphs.runtime import invoke

        gateway = FakeGateway(profile=SUMMARY_FAKE_PROFILE)
        gateway.route = lambda request: text
        result = await invoke(_graph(gateway), _invocation("Wren", ["obs:1 road: quiet"]))
        assert result["status"] == "proposed"
        assert result["proposal"]["text"] == "Wren watched the road."
        assert result["fallback"] is False

    _run(_inner())


def test_graph_rejects_unknown_sources() -> None:
    text = json.dumps({"text": "Wren flew.", "source_ids": ["obs:999"]})

    async def _inner() -> None:
        from worldsim.application.graphs.runtime import invoke

        gateway = FakeGateway(profile=SUMMARY_FAKE_PROFILE)
        gateway.route = lambda request: text
        result = await invoke(_graph(gateway), _invocation("Wren", ["obs:1 road: quiet"]))
        assert result["status"] == "fallback"
        assert "obs:999" in result["fallback_reason"]

    _run(_inner())


def test_graph_outage_falls_back() -> None:
    def _route(request: Any) -> str | None:
        raise ModelUnavailableError("provider down")

    async def _inner() -> None:
        from worldsim.application.graphs.runtime import invoke

        gateway = FakeGateway(profile=SUMMARY_FAKE_PROFILE)
        gateway.route = _route
        result = await invoke(_graph(gateway), _invocation("Wren", ["obs:1 road: quiet"]))
        assert result["status"] == "fallback"
        assert result["proposal"] is None

    _run(_inner())


def test_day_range_and_fallback_text() -> None:
    assert day_range(1) == (0, 9)
    assert day_range(2) == (10, 19)
    assert "2 observations" in fallback_text(2, 0)


async def _seed_summary_world() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            home = new_location_id()
            wren = new_character_id()
            ash = new_character_id()
            run_id = new_phase_run_id()
            await uow.worlds.add(World(id=wid, name="Vale", seed_version="s2-test"))
            await uow.locations.add(Location(id=home, world_id=wid, name="Hearth", capacity=4))
            for cid, name in ((wren, "Wren"), (ash, "Ash")):
                await uow.characters.add_identity(cid, wid, name)
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=wid,
                        name=name,
                        card_version=1,
                        location_id=home,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
            await uow.phases.create_run(PhaseRun(id=run_id, world_id=wid, absolute_index=9))
            sequence = await uow.events.max_sequence(wid) + 1
            event_id = uuid4()
            await uow.events.append_event(
                WorldEvent(
                    id=event_id,
                    world_id=wid,
                    sequence=sequence,
                    event_type=EventType.WORLD_TICKED,
                    absolute_index=9,
                    phase_run_id=run_id,
                    participant_ids=[],
                    summary={"note": "tick"},
                )
            )
            await uow.perception.add_observation(
                Observation(
                    id=uuid4(),
                    world_id=wid,
                    event_id=event_id,
                    observer_character_id=wren,
                    facts=[ObservationFact(key="road", value="quiet at dawn")],
                    created_phase_index=2,
                )
            )
            await uow.perception.add_observation(
                Observation(
                    id=uuid4(),
                    world_id=wid,
                    event_id=event_id,
                    observer_character_id=ash,
                    facts=[ObservationFact(key="market", value="bustling at noon")],
                    created_phase_index=5,
                )
            )
            await uow.commit()
            return {"world": wid, "run": run_id, "wren": wren, "ash": ash}
    finally:
        await engine.dispose()


def _orchestrator(gateway: FakeGateway) -> Any:
    from worldsim.application.orchestration.stage1 import Stage1Orchestrator
    from worldsim.application.tasks.service import TaskService
    from worldsim.application.tracing.service import TraceService
    from worldsim.application.transactions.canonical import CanonicalTransaction
    from worldsim.infrastructure.model_gateway.profiles import (
        CHARACTER_FAKE_PROFILE,
        DIRECTOR_FAKE_PROFILE,
        NARRATOR_FAKE_PROFILE,
        REACTION_FAKE_PROFILE,
        RESOLVER_FAKE_PROFILE,
        SUMMARY_FAKE_PROFILE,
    )
    from worldsim.infrastructure.tracing.langsmith import NullExporter

    engine = create_engine(Settings())
    factory = lambda: create_unit_of_work(engine)  # noqa: E731
    return Stage1Orchestrator(
        factory,
        CanonicalTransaction(factory),
        TaskService(factory),
        TraceService(factory, NullExporter()),
        lambda role: gateway,
        {
            "character": CHARACTER_FAKE_PROFILE,
            "reaction": REACTION_FAKE_PROFILE,
            "resolver": RESOLVER_FAKE_PROFILE,
            "narrator": NARRATOR_FAKE_PROFILE,
            "director": DIRECTOR_FAKE_PROFILE,
            "summary": SUMMARY_FAKE_PROFILE,
        },
    )


def test_midnight_summaries_differ_by_owner(migrated_db: None) -> None:
    texts = {
        "Wren": "Wren kept the dawn watch; the road stayed quiet.",
        "Ash": "Ash haggled at noon; the market bustled.",
    }

    def _route(request: Any) -> str | None:
        prompt = request.prompt if isinstance(request.prompt, str) else ""
        for owner, text in texts.items():
            if f"{owner}'s sources" in prompt:
                return json.dumps({"text": text, "source_ids": []})
        return None

    gateway = FakeGateway(profile=SUMMARY_FAKE_PROFILE)
    gateway.route = _route

    async def _inner() -> None:
        ids = await _seed_summary_world()
        orch = _orchestrator(gateway)
        written = await orch._summarize_day(ids["world"], ids["run"], 9, 1)
        assert written == 2
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                wren = await uow.summaries.list_for_owner(ids["world"], ids["wren"])
                ash = await uow.summaries.list_for_owner(ids["world"], ids["ash"])
                assert [s.text for s in wren] == [texts["Wren"]]
                assert [s.text for s in ash] == [texts["Ash"]]
                assert wren[0].source_ids != ash[0].source_ids
                assert all(s.source_ids for s in wren + ash)
                assert all(s.version == 1 for s in wren + ash)
                # Raw records survive untouched.
                assert len(await uow.perception.observations_for_observer(ids["wren"], 20)) == 1
            # Regeneration versions instead of replacing.
            written_again = await orch._summarize_day(ids["world"], ids["run"], 9, 1)
            assert written_again == 2
            async with create_unit_of_work(engine) as uow:
                wren = await uow.summaries.list_for_owner(ids["world"], ids["wren"])
                assert [s.version for s in wren] == [1, 2]
        finally:
            await engine.dispose()

    _run(_inner())


def test_summary_outage_records_fallback(migrated_db: None) -> None:
    def _route(request: Any) -> str | None:
        raise ModelUnavailableError("provider down")

    gateway = FakeGateway(profile=SUMMARY_FAKE_PROFILE)
    gateway.route = _route

    async def _inner() -> None:
        ids = await _seed_summary_world()
        orch = _orchestrator(gateway)
        written = await orch._summarize_day(ids["world"], ids["run"], 9, 1)
        assert written == 2
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                wren = await uow.summaries.list_for_owner(ids["world"], ids["wren"])
                assert wren[0].fallback is True
                assert "1 observations" in wren[0].text
        finally:
            await engine.dispose()

    _run(_inner())
