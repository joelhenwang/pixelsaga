"""Atomic scene commit checks (owned by S1-COMMIT-001)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from uuid import UUID

import pytest

from worldsim.application.transactions.canonical import CanonicalTransaction, MemorySpec
from worldsim.application.transactions.scenes import (
    NARRATION_OUTBOX_KIND,
    build_scene_commit,
    observation_spec,
)
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.commands import MoveAction, WaitAction
from worldsim.domain.effects import (
    DomainEffect,
    MoveEntityEffect,
    ResourceAdjustedEffect,
)
from worldsim.domain.enums import (
    EventType,
    ResolutionOutcome,
    ResolverKind,
    ResourceKind,
)
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    new_attempt_id,
    new_card_id,
    new_character_id,
    new_command_id,
    new_intent_id,
    new_location_id,
    new_phase_run_id,
    new_reaction_id,
    new_resolution_id,
    new_snapshot_id,
    new_world_id,
)
from worldsim.domain.perception import ObservableEvent, PerceivedFact
from worldsim.domain.phases import PhaseRun, PhaseSnapshot, SnapshotCharacter
from worldsim.domain.rules.perception import permitted_facts
from worldsim.domain.rules.scenes import assemble_scenes
from worldsim.domain.scenes import Attempt, Intent, Reaction, Resolution, Scene
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


@asynccontextmanager
async def _service(
    hook: Callable[[str], None] | None = None,
) -> AsyncGenerator[CanonicalTransaction]:
    engine = create_engine(Settings())
    try:
        yield CanonicalTransaction(lambda: create_unit_of_work(engine), pre_commit_hook=hook)
    finally:
        await engine.dispose()


async def _seed() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            await uow.worlds.add(World(id=wid, name="Commit", seed_version="s1-test"))
            hearth, market, route = new_location_id(), new_location_id(), uuid.uuid4()
            await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth"))
            await uow.locations.add(
                Location(
                    id=market,
                    world_id=wid,
                    name="Market",
                    routes=[],
                )
            )
            wren, ash = new_character_id(), new_character_id()
            for cid, name, place, stamina in (
                (wren, "Wren", hearth, 80),
                (ash, "Ash", market, 70),
            ):
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
                        stamina=stamina,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
            await uow.versions.ensure(wid, wid, "world")
            run_id = new_phase_run_id()
            await uow.phases.create_run(PhaseRun(id=run_id, world_id=wid, absolute_index=3))
            snapshot_id = new_snapshot_id()
            await uow.phases.add_snapshot(
                PhaseSnapshot(
                    id=snapshot_id,
                    world_id=wid,
                    phase_run_id=run_id,
                    absolute_index=3,
                    world_version=0,
                    characters=[
                        SnapshotCharacter(character_id=wren, version=0),
                        SnapshotCharacter(character_id=ash, version=0),
                    ],
                    content_hash="c" * 64,
                )
            )
            await uow.commit()
            return {
                "world": wid,
                "wren": wren,
                "ash": ash,
                "hearth": hearth,
                "market": market,
                "route": route,
                "run": run_id,
                "snapshot": snapshot_id,
            }
    finally:
        await engine.dispose()


def _intents(ids: dict[str, UUID]) -> tuple[Intent, Intent]:
    snapshot = ids["snapshot"]
    move = Intent(
        id=new_intent_id(),
        world_id=ids["world"],
        snapshot_id=snapshot,
        phase_run_id=ids["run"],
        author_character_id=ids["wren"],
        action=MoveAction(
            character_id=ids["wren"],
            snapshot_id=snapshot,
            destination_location_id=ids["market"],
            route_id=ids["route"],
        ),
        idempotency_key=f"move:{uuid.uuid4()}",
    )
    wait = Intent(
        id=new_intent_id(),
        world_id=ids["world"],
        snapshot_id=snapshot,
        phase_run_id=ids["run"],
        author_character_id=ids["ash"],
        action=WaitAction(character_id=ids["ash"], snapshot_id=snapshot),
        idempotency_key=f"wait:{uuid.uuid4()}",
    )
    return move, wait


def _effects(ids: dict[str, UUID]) -> list[DomainEffect]:
    wren = ids["wren"]
    return [
        MoveEntityEffect(
            affected_ids=[wren],
            expected_versions={str(wren): 0},
            from_location_id=ids["hearth"],
            to_location_id=ids["market"],
            route_id=ids["route"],
        ),
        ResourceAdjustedEffect(
            affected_ids=[wren],
            expected_versions={str(wren): 0},
            resource=ResourceKind.STAMINA,
            delta=-10,
        ),
    ]


def _scene_bundle(
    ids: dict[str, UUID],
) -> tuple[Scene, Intent, Intent, Attempt, Reaction, Resolution]:
    from worldsim.domain.rules.views import WorldView

    move, wait = _intents(ids)
    view = WorldView(
        world=World(id=ids["world"], name="Commit", seed_version="s1-test"),
        characters=[
            Character(
                id=ids["wren"],
                world_id=ids["world"],
                name="Wren",
                card_version=1,
                location_id=ids["hearth"],
                stamina=80,
                mana=40,
            ),
            Character(
                id=ids["ash"],
                world_id=ids["world"],
                name="Ash",
                card_version=1,
                location_id=ids["market"],
                stamina=70,
                mana=40,
            ),
        ],
        locations=[
            Location(id=ids["hearth"], world_id=ids["world"], name="Hearth"),
            Location(id=ids["market"], world_id=ids["world"], name="Market"),
        ],
    )
    scenes = assemble_scenes(
        [move, wait],
        view,
        world_id=ids["world"],
        phase_run_id=ids["run"],
        snapshot_id=ids["snapshot"],
    )
    assert len(scenes) == 1
    scene = scenes[0]
    attempt = Attempt(
        id=new_attempt_id(),
        world_id=ids["world"],
        intent_id=move.id,
        scene_id=scene.id,
        actor_character_id=ids["wren"],
        observable_summary="Wren heads for the market.",
    )
    reaction = Reaction(
        id=new_reaction_id(),
        world_id=ids["world"],
        attempt_id=attempt.id,
        scene_id=scene.id,
        reactor_character_id=ids["ash"],
        action=WaitAction(character_id=ids["ash"], snapshot_id=ids["snapshot"]),
    )
    resolution = Resolution(
        id=new_resolution_id(),
        world_id=ids["world"],
        scene_id=scene.id,
        outcome=ResolutionOutcome.SUCCESS,
        resolver=ResolverKind.DETERMINISTIC,
        effects=_effects(ids),
        rationale="Wren walks to the market.",
        random_seed=7,
    )
    return scene, move, wait, attempt, reaction, resolution


def _permitted_for_ash(ids: dict[str, UUID]) -> list[PerceivedFact]:
    event = ObservableEvent(
        event_id=uuid.uuid4(),
        world_id=ids["world"],
        location_id=ids["market"],
        participant_ids=[ids["wren"]],
        facts=[PerceivedFact(key="arrival", value="Wren arrives")],
    )
    return permitted_facts(event, ids["ash"], ids["market"])


def test_scene_commit_creates_one_atomic_result(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        scene, move, wait, attempt, reaction, resolution = _scene_bundle(ids)
        permitted = _permitted_for_ash(ids)
        async with _service() as tx:
            result = await tx.commit(
                build_scene_commit(
                    command_id=new_command_id(),
                    scene=scene,
                    intents=[move, wait],
                    attempts=[attempt],
                    reactions=[reaction],
                    resolution=resolution,
                    effects=list(resolution.effects),
                    expected_versions={str(ids["wren"]): 0, str(ids["ash"]): 0},
                    absolute_index=3,
                    observations=[observation_spec(ids["ash"], list(permitted))],
                    memories=[
                        MemorySpec(owner_id=ids["wren"], text="I walked.", observation_index=None)
                    ],
                )
            )
        assert not result.duplicate
        assert result.effect_count == 2
        assert len(result.observation_ids) == 1
        assert len(result.memory_ids) == 1
        assert len(result.outbox_ids) == 1
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                stored_scene = await uow.scenes.get_scene(scene.id)
                assert stored_scene.status.value == "committed"
                assert stored_scene.event_id == result.event_id
                assert {str(i) for i in stored_scene.intent_ids} == {str(move.id)}
                assert (await uow.scenes.get_intent(move.id)).status.value == "validated"
                assert (await uow.scenes.get_attempt(attempt.id)).status.value == "committed"
                stored_resolution = await uow.scenes.get_resolution(scene.id)
                assert stored_resolution.outcome.value == "success"
                assert stored_resolution.random_seed == 7
                observations = await uow.perception.observations_for_event(result.event_id)
                assert [(f.key, f.value) for o in observations for f in o.facts] == [
                    ("arrival", "Wren arrives")
                ]
                assert (await uow.characters.get(ids["wren"])).stamina == 70
                assert await uow.outbox.count_pending(ids["world"]) == 1
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_fault_at_each_scene_boundary_rolls_back(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        scene_ids: list[UUID] = []
        for point in (
            "after_command",
            "after_effects",
            "after_scene",
            "after_projections",
            "after_perception",
            "after_outbox",
        ):
            scene, move, wait, attempt, reaction, resolution = _scene_bundle(ids)
            scene_ids.append(scene.id)

            def _hook(_point: str, _wanted: str = point) -> None:
                if _point == _wanted:
                    raise RuntimeError(f"injected at {_point}")

            async with _service(hook=_hook) as tx:
                with pytest.raises(RuntimeError, match="injected"):
                    await tx.commit(
                        build_scene_commit(
                            command_id=new_command_id(),
                            scene=scene,
                            intents=[move, wait],
                            attempts=[attempt],
                            reactions=[reaction],
                            resolution=resolution,
                            effects=list(resolution.effects),
                            expected_versions={str(ids["wren"]): 0, str(ids["ash"]): 0},
                            absolute_index=3,
                        )
                    )
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(ids["world"]) == 0
                assert await uow.versions.get(ids["wren"]) == 0
                assert await uow.outbox.count_pending(ids["world"]) == 0
                for scene_id in scene_ids:
                    with pytest.raises(DomainError):
                        await uow.scenes.get_scene(scene_id)
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_stale_scene_versions_reject(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        scene, move, wait, attempt, reaction, resolution = _scene_bundle(ids)
        async with _service() as tx:
            with pytest.raises(DomainError) as excinfo:
                await tx.commit(
                    build_scene_commit(
                        command_id=new_command_id(),
                        scene=scene,
                        intents=[move, wait],
                        attempts=[attempt],
                        reactions=[reaction],
                        resolution=resolution,
                        effects=list(resolution.effects),
                        expected_versions={str(ids["wren"]): 9, str(ids["ash"]): 0},
                        absolute_index=3,
                    )
                )
            assert excinfo.value.code is ErrorCode.VERSION_CONFLICT
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(ids["world"]) == 0
                with pytest.raises(DomainError):
                    await uow.scenes.get_scene(scene.id)
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_duplicate_scene_returns_stored_result(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        scene, move, wait, attempt, reaction, resolution = _scene_bundle(ids)
        request = build_scene_commit(
            command_id=new_command_id(),
            scene=scene,
            intents=[move, wait],
            attempts=[attempt],
            reactions=[reaction],
            resolution=resolution,
            effects=list(resolution.effects),
            expected_versions={str(ids["wren"]): 0, str(ids["ash"]): 0},
            absolute_index=3,
        )
        async with _service() as tx:
            first = await tx.commit(request)
            second = await tx.commit(request)
        assert not first.duplicate
        assert second.duplicate
        assert second.event_id == first.event_id
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(ids["world"]) == 1
                assert (await uow.scenes.get_scene(scene.id)).event_id == first.event_id
                assert (await uow.scenes.get_attempt(attempt.id)).status.value == "committed"
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_narration_outbox_only_after_commit(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        scene, move, wait, attempt, reaction, resolution = _scene_bundle(ids)

        def _hook(_point: str) -> None:
            if _point == "after_outbox":
                raise RuntimeError("injected at after_outbox")

        async with _service(hook=_hook) as tx:
            with pytest.raises(RuntimeError, match="injected"):
                await tx.commit(
                    build_scene_commit(
                        command_id=new_command_id(),
                        scene=scene,
                        intents=[move, wait],
                        attempts=[attempt],
                        reactions=[reaction],
                        resolution=resolution,
                        effects=list(resolution.effects),
                        expected_versions={str(ids["wren"]): 0, str(ids["ash"]): 0},
                        absolute_index=3,
                    )
                )
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                assert await uow.outbox.count_pending(ids["world"]) == 0
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_narration_outbox_kind(migrated_db: None) -> None:
    assert NARRATION_OUTBOX_KIND == "narrate_scene"
    assert EventType.ACTION_RESOLVED.value == "action_resolved"
