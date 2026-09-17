"""Director restraint: triggers, privileges, budgets, safe fallback (owned by S2-DIRECTOR-001)."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from worldsim.application.graphs.director import (
    DirectorGraphDeps,
    build_director_graph,
    load_director_prompt,
)
from worldsim.application.graphs.state import GraphInvocation
from worldsim.application.ports.model_gateway import ModelUnavailableError
from worldsim.domain.characters import Character
from worldsim.domain.director import (
    DIRECTOR_COOLDOWN_PHASES,
    DirectorProposal,
    should_trigger,
    validate_proposal,
)
from worldsim.domain.enums import PhaseRunState
from worldsim.domain.ids import (
    new_arc_id,
    new_character_id,
    new_hook_id,
    new_location_id,
    new_phase_run_id,
    new_world_id,
)
from worldsim.domain.phases import PhaseRun
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import DIRECTOR_FAKE_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def test_trigger_respects_cooldown() -> None:
    assert should_trigger(1, None) is True
    assert should_trigger(4, 1) is True
    assert should_trigger(3, 1) is False
    assert should_trigger(2, 1, cooldown=1) is True
    assert DIRECTOR_COOLDOWN_PHASES == 3


def test_validation_rejects_overreach() -> None:
    wid = new_world_id()
    known = frozenset({new_character_id()})
    denied = validate_proposal(
        DirectorProposal(
            action="propose_hook",
            title="A shadow falls",
            requested_powers=["kill_character"],
            participant_ids=[],
        ),
        wid,
        known,
        0,
        0,
        new_hook_id(),
        new_arc_id(),
    )
    assert denied.accepted is False and "kill_character" in denied.reason
    stranger = validate_proposal(
        DirectorProposal(
            action="propose_hook",
            title="A stranger arrives",
            participant_ids=[new_character_id()],
        ),
        wid,
        known,
        0,
        0,
        new_hook_id(),
        new_arc_id(),
    )
    assert stranger.accepted is False and "known characters" in stranger.reason
    full = validate_proposal(
        DirectorProposal(action="propose_hook", title="One more"),
        wid,
        known,
        3,
        0,
        new_hook_id(),
        new_arc_id(),
    )
    assert full.accepted is False and "budget" in full.reason
    noop = validate_proposal(
        DirectorProposal(action="noop", reason="quiet suits them"),
        wid,
        known,
        0,
        0,
        new_hook_id(),
        new_arc_id(),
    )
    assert noop.accepted is False


def _graph(gateway: FakeGateway) -> Any:
    return build_director_graph(
        DirectorGraphDeps(
            gateway=gateway,
            profile=DIRECTOR_FAKE_PROFILE,
            system_template=load_director_prompt(),
        )
    )


def _invocation(world_id: UUID, run_id: UUID) -> GraphInvocation:
    from worldsim.domain.ids import new_task_id

    return GraphInvocation(
        graph_name="director-proposal",
        graph_version="v1",
        task_run_id=new_task_id(),
        world_id=world_id,
        phase_run_id=run_id,
        snapshot_id=new_task_id(),
        role="director",
        profile_version=DIRECTOR_FAKE_PROFILE.version,
        prompt_version="director.v1",
        input={
            "world_summary": "Phase 4. Characters: Wren, Ash. Places: Hearth.",
            "trigger_ok": True,
            "known_character_ids": [],
            "active_hooks": 0,
            "active_arcs": 0,
            "hook_id": str(new_hook_id()),
            "arc_id": str(new_arc_id()),
            "world_id": str(world_id),
        },
    )


def test_graph_noop_without_trigger() -> None:
    gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)

    async def _inner() -> None:
        from worldsim.application.graphs.runtime import invoke

        wid = new_world_id()
        invocation = _invocation(wid, new_phase_run_id())
        invocation.input["trigger_ok"] = False
        invocation.input["trigger_reason"] = "cooldown active"
        result = await invoke(_graph(gateway), invocation)
        assert result["status"] == "noop"
        assert result["proposal"] is None

    _run(_inner())


def test_graph_outage_is_noop() -> None:
    def _route(request: Any) -> str | None:
        raise ModelUnavailableError("provider down")

    gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
    gateway.route = _route

    async def _inner() -> None:
        from worldsim.application.graphs.runtime import invoke

        result = await invoke(_graph(gateway), _invocation(new_world_id(), new_phase_run_id()))
        assert result["status"] == "noop"
        assert "unavailable" in result["decision"]["reason"].lower()

    _run(_inner())


def test_graph_proposes_and_validates() -> None:
    proposal: dict[str, Any] = {
        "action": "propose_hook",
        "title": "A peddler arrives",
        "purpose": "Trade news for rumors.",
        "requested_powers": [],
        "participant_ids": [],
        "reason": "",
    }

    def _route(request: Any) -> str | None:
        if "You direct" in (request.system or ""):
            return json.dumps(proposal)
        return None

    gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
    gateway.route = _route

    async def _inner() -> None:
        from worldsim.application.graphs.runtime import invoke

        result = await invoke(_graph(gateway), _invocation(new_world_id(), new_phase_run_id()))
        assert result["status"] == "proposed"
        assert result["decision"]["accepted"] is True
        assert result["decision"]["hook"]["title"] == "A peddler arrives"

    _run(_inner())


async def _seed_director_world() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            home = new_location_id()
            wren = new_character_id()
            run_id = new_phase_run_id()
            await uow.worlds.add(World(id=wid, name="Vale", seed_version="s2-test"))
            await uow.locations.add(Location(id=home, world_id=wid, name="Hearth", capacity=4))
            await uow.characters.add_identity(wren, wid, "Wren")
            await uow.characters.add_state(
                Character(
                    id=wren,
                    world_id=wid,
                    name="Wren",
                    card_version=1,
                    location_id=home,
                    stamina=80,
                    mana=40,
                )
            )
            await uow.versions.ensure(wren, wid, "character")
            await uow.phases.create_run(PhaseRun(id=run_id, world_id=wid, absolute_index=4))
            await uow.commit()
            return {"world": wid, "run": run_id, "wren": wren}
    finally:
        await engine.dispose()


def _orchestrator(gateway: FakeGateway) -> Any:
    from worldsim.application.orchestration.stage1 import Stage1Orchestrator
    from worldsim.application.tasks.service import TaskService
    from worldsim.application.tracing.service import TraceService
    from worldsim.application.transactions.canonical import CanonicalTransaction
    from worldsim.infrastructure.model_gateway.profiles import (
        CHARACTER_FAKE_PROFILE,
        NARRATOR_FAKE_PROFILE,
        REACTION_FAKE_PROFILE,
        RESOLVER_FAKE_PROFILE,
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
        },
    )


def test_director_phase_accepts_and_records(migrated_db: None) -> None:
    proposal: dict[str, Any] = {
        "action": "propose_hook",
        "title": "A peddler arrives",
        "purpose": "Trade news for rumors.",
        "requested_powers": [],
        "participant_ids": [],
        "reason": "",
    }

    def _route(request: Any) -> str | None:
        if "You direct" in (request.system or ""):
            return json.dumps(proposal)
        return None

    gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
    gateway.route = _route

    async def _inner() -> None:
        from worldsim.application.orchestration.stage1 import SealedPhase

        ids = await _seed_director_world()
        orch = _orchestrator(gateway)
        engine = create_engine(Settings())
        try:
            sealed = SealedPhase(snapshot_id=ids["run"], versions={}, locations={})
            status = await orch._director_phase(ids["world"], ids["run"], 4, sealed)
            assert status == "proposed"
            async with create_unit_of_work(engine) as uow:
                hooks = await uow.narrative.list_hooks_for_world(ids["world"])
                assert [h.title for h in hooks] == ["A peddler arrives"]
                assert hooks[0].created_phase_index == 4
                config = await uow.worlds.get_config(ids["world"])
                assert config.get("director.last_absolute") == 4
                run = await uow.phases.get_run(ids["run"])
                assert run.state.value == PhaseRunState.DIRECTOR_COMPLETE.value
            # Cooldown now skips the next phases without a model call.
            gateway.route = None
            status = await orch._director_phase(ids["world"], ids["run"], 5, sealed)
            assert status == "skipped"
        finally:
            await engine.dispose()

    _run(_inner())
