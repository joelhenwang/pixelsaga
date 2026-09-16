"""Post-commit NarrationGraph checks (owned by S1-NARRATE-001)."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest

from worldsim.application.graphs.narrate import (
    NARRATOR_PROMPT_VERSION,
    NarratorGraphDeps,
    build_narration_graph,
    load_narrator_prompt,
)
from worldsim.application.graphs.runtime import invoke
from worldsim.application.graphs.state import GraphInvocation
from worldsim.application.ports.model_gateway import ModelUnavailableError
from worldsim.domain.errors import DomainError
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import NARRATOR_FAKE_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings

FACTS = [
    {"key": "arrival", "value": "Wren arrives at the market"},
    {"key": "greeting", "value": "Ash waves"},
]


def _deps(gateway: FakeGateway) -> NarratorGraphDeps:
    return NarratorGraphDeps(
        gateway=gateway, profile=NARRATOR_FAKE_PROFILE, system_template=load_narrator_prompt()
    )


def _invocation(event_id: uuid.UUID, **overrides: Any) -> GraphInvocation:
    payload: dict[str, Any] = {
        "event_id": str(event_id),
        "event_committed": True,
        "audience_ids": [],
        "visible_facts": FACTS,
        "beats_budget": 8,
    }
    payload.update(overrides)
    return GraphInvocation(
        graph_name="narrate",
        graph_version="v1",
        task_run_id=uuid.uuid4(),
        world_id=uuid.uuid4(),
        phase_run_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        scene_id=uuid.uuid4(),
        role="narrator",
        profile_version=NARRATOR_FAKE_PROFILE.version,
        prompt_version=NARRATOR_PROMPT_VERSION,
        input=payload,
    )


def _beat(text: str, cited: list[str], speaker: str | None = None) -> dict[str, Any]:
    return {"speaker_id": speaker, "text": text, "cited_fact_keys": cited}


def test_valid_beats_accepted_with_event_linkage() -> None:
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_text(
        json.dumps([_beat("Wren arrives.", ["arrival"]), _beat("Ash waves.", ["greeting"])])
    )

    result = asyncio.run(invoke(build_narration_graph(_deps(gateway)), _invocation(event_id)))

    assert result["status"] == "narrated"
    assert result["proposal"]["fallback"] is False
    beats = result["proposal"]["beats"]
    assert len(beats) == 2
    assert {b["source_event_id"] for b in beats} == {str(event_id)}
    assert all(b["id"] for b in beats)
    assert beats[0]["cited_fact_keys"] == ["arrival"]


def test_unsupported_fact_repaired_once() -> None:
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_text(json.dumps([_beat("Dragons land.", ["dragons"])]))
    gateway.enqueue_text(json.dumps([_beat("Wren arrives.", ["arrival"])]))

    result = asyncio.run(invoke(build_narration_graph(_deps(gateway)), _invocation(event_id)))

    assert result["status"] == "narrated"
    assert result["repair_count"] == 1
    assert result["proposal"]["beats"][0]["cited_fact_keys"] == ["arrival"]


def test_repeated_unsupported_falls_back_to_facts() -> None:
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_text(json.dumps([_beat("Dragons land.", ["dragons"])]))
    gateway.enqueue_text(json.dumps([_beat("Kings fall.", ["kings"])]))

    result = asyncio.run(invoke(build_narration_graph(_deps(gateway)), _invocation(event_id)))

    assert result["status"] == "fallback"
    assert result["proposal"]["fallback"] is True
    beats = result["proposal"]["beats"]
    assert {tuple(b["cited_fact_keys"]) for b in beats} == {("arrival",), ("greeting",)}
    assert {b["source_event_id"] for b in beats} == {str(event_id)}


def test_outsider_speaker_rejected() -> None:
    event_id = uuid.uuid4()
    outsider = str(uuid.uuid4())
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_text(json.dumps([_beat("I speak.", ["arrival"], speaker=outsider)]))
    gateway.enqueue_text(json.dumps([_beat("Wren arrives.", ["arrival"])]))
    result = asyncio.run(invoke(build_narration_graph(_deps(gateway)), _invocation(event_id)))

    assert result["status"] == "narrated"
    assert result["repair_count"] == 1


def test_model_outage_uses_structured_fallback() -> None:
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_error(ModelUnavailableError("provider down"))

    result = asyncio.run(invoke(build_narration_graph(_deps(gateway)), _invocation(event_id)))

    assert result["status"] == "fallback"
    beats = result["proposal"]["beats"]
    assert len(beats) == 2
    assert "arrival" in beats[0]["text"]


def test_uncommitted_event_refused_without_call() -> None:
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)

    with pytest.raises(DomainError):
        asyncio.run(
            invoke(
                build_narration_graph(_deps(gateway)), _invocation(event_id, event_committed=False)
            )
        )
    assert gateway.sent_requests == []


def test_beat_budget_enforced() -> None:
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_text(
        json.dumps(
            [
                _beat("One.", ["arrival"]),
                _beat("Two.", ["greeting"]),
                _beat("Three.", ["arrival"]),
            ]
        )
    )
    gateway.enqueue_text(json.dumps([_beat("One.", ["arrival"])]))

    result = asyncio.run(
        invoke(build_narration_graph(_deps(gateway)), _invocation(event_id, beats_budget=1))
    )

    assert result["status"] == "narrated"
    assert len(result["proposal"]["beats"]) == 1


def test_narration_persistence_leaves_projections(migrated_db: None) -> None:
    async def _inner() -> None:
        from worldsim.application.transactions.canonical import (
            CanonicalTransaction,
            CommitRequest,
            canonical_input_hash,
        )
        from worldsim.domain.characters import Character, CharacterCard
        from worldsim.domain.enums import EventType
        from worldsim.domain.ids import (
            new_card_id,
            new_character_id,
            new_command_id,
            new_location_id,
            new_phase_run_id,
            new_world_id,
        )
        from worldsim.domain.narration import NarrationBeat
        from worldsim.domain.phases import PhaseRun
        from worldsim.domain.world import Location, World

        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Narr", seed_version="s1-test"))
                home = new_location_id()
                await uow.locations.add(Location(id=home, world_id=wid, name="Hearth"))
                cid = new_character_id()
                await uow.characters.add_identity(cid, wid, "Wren")
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=cid, name="W", version=1)
                )
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=wid,
                        name="Wren",
                        card_version=1,
                        location_id=home,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
                await uow.versions.ensure(wid, wid, "world")
                run_id = new_phase_run_id()
                await uow.phases.create_run(PhaseRun(id=run_id, world_id=wid, absolute_index=1))
                await uow.commit()
            key = "narrate-probe"
            payload: dict[str, object] = {"note": "probe"}
            tx = CanonicalTransaction(lambda: create_unit_of_work(engine))
            result = await tx.commit(
                CommitRequest(
                    command_id=new_command_id(),
                    world_id=wid,
                    idempotency_key=key,
                    actor_role="system",
                    command_type="advance_phase",
                    expected_versions={str(wid): 0, str(cid): 0},
                    payload=payload,
                    input_hash=canonical_input_hash(
                        {"key": key, "payload": payload, "effects": []}
                    ),
                    absolute_index=1,
                    phase_run_id=run_id,
                    event_type=EventType.WORLD_TICKED,
                    effects=[],
                )
            )
            beat = NarrationBeat(
                id=uuid.uuid4(),
                world_id=wid,
                source_event_id=result.event_id,
                cited_fact_keys=["arrival"],
                text="Wren arrives.",
            )
            async with create_unit_of_work(engine) as uow:
                await uow.scenes.save_narration(beat)
                await uow.commit()
            async with create_unit_of_work(engine) as uow:
                stored = await uow.scenes.narrations_for_event(result.event_id)
                assert [b.text for b in stored] == ["Wren arrives."]
                assert stored[0].cited_fact_keys == ["arrival"]
                # Narration changed nothing canonical.
                assert (await uow.characters.get(cid)).version == 0
                assert (await uow.characters.get(cid)).stamina == 80
                assert await uow.events.count_events(wid) == 1
        finally:
            await engine.dispose()

    asyncio.run(_inner())
