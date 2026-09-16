"""Deterministic scene assembly checks (owned by S1-SCENE-001)."""

from __future__ import annotations

import uuid

from worldsim.domain.characters import Character
from worldsim.domain.commands import (
    CommunicateAction,
    MoveAction,
    RestAction,
    WaitAction,
)
from worldsim.domain.enums import ParticipantRole
from worldsim.domain.ids import new_location_id, new_world_id
from worldsim.domain.rules.scenes import (
    assemble_scenes,
    mutable_aggregates,
    scenes_overlap,
)
from worldsim.domain.rules.views import WorldView
from worldsim.domain.scenes import DesiredEffect, Intent, Scene
from worldsim.domain.world import Location, World


def _world() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    wid = new_world_id()
    hearth_id, market_id = new_location_id(), new_location_id()
    wren_id, ash_id = uuid.uuid4(), uuid.uuid4()
    return wid, hearth_id, market_id, wren_id, ash_id


def _view(
    wid: uuid.UUID,
    hearth_id: uuid.UUID,
    market_id: uuid.UUID,
    wren_id: uuid.UUID,
    ash_id: uuid.UUID,
) -> WorldView:
    def character(cid: uuid.UUID, name: str, place: uuid.UUID) -> Character:
        return Character(
            id=cid,
            world_id=wid,
            name=name,
            card_version=1,
            location_id=place,
            stamina=80,
            mana=40,
        )

    return WorldView(
        world=World(id=wid, name="Vale", seed_version="s1-test"),
        characters=[
            character(wren_id, "Wren", hearth_id),
            character(ash_id, "Ash", market_id),
        ],
        locations=[
            Location(id=hearth_id, world_id=wid, name="Hearth"),
            Location(id=market_id, world_id=wid, name="Market"),
        ],
    )


def _intent(
    author: uuid.UUID,
    action: object,
    snapshot: uuid.UUID,
    effects: list[DesiredEffect] | None = None,
) -> Intent:
    return Intent(
        id=uuid.uuid4(),
        world_id=uuid.uuid4(),
        snapshot_id=snapshot,
        phase_run_id=uuid.uuid4(),
        author_character_id=author,
        action=action,  # type: ignore[arg-type]
        desired_effects=effects or [],
        idempotency_key=f"test:{uuid.uuid4()}",
    )


def _assemble(intents: list[Intent], view: WorldView, snapshot: uuid.UUID) -> list[Scene]:
    wid = view.world.id
    return assemble_scenes(
        intents,
        view,
        world_id=wid,
        phase_run_id=uuid.uuid4(),
        snapshot_id=snapshot,
    )


def test_compatible_meeting_forms_one_scene() -> None:
    wid, hearth, market, wren, ash = _world()
    view = _view(wid, hearth, market, wren, ash)
    snapshot = uuid.uuid4()
    move = _intent(
        wren,
        MoveAction(character_id=wren, snapshot_id=snapshot, destination_location_id=market),
        snapshot,
    )
    wait = _intent(ash, WaitAction(character_id=ash, snapshot_id=snapshot), snapshot)
    scenes = _assemble([move, wait], view, snapshot)
    assert len(scenes) == 1
    assert {i for i in scenes[0].intent_ids} == {move.id, wait.id}
    assert scenes[0].beat_budget == 8


def test_mutual_appointment_forms_one_scene() -> None:
    wid, hearth, market, wren, ash = _world()
    view = _view(wid, hearth, market, wren, ash)
    snapshot = uuid.uuid4()
    first = _intent(
        wren,
        CommunicateAction(
            character_id=wren,
            snapshot_id=snapshot,
            target_character_id=ash,
            topic="the road",
        ),
        snapshot,
    )
    second = _intent(
        ash,
        CommunicateAction(
            character_id=ash,
            snapshot_id=snapshot,
            target_character_id=wren,
            topic="the road",
        ),
        snapshot,
    )
    scenes = _assemble([first, second], view, snapshot)
    assert len(scenes) == 1
    roles = {p.character_id: p.role for p in scenes[0].participants}
    assert roles[wren] == ParticipantRole.INITIATOR
    assert roles[ash] == ParticipantRole.INITIATOR


def test_conflicting_target_forms_one_scene() -> None:
    wid, hearth, market, wren, ash = _world()
    view = _view(wid, hearth, market, wren, ash)
    snapshot = uuid.uuid4()
    sage = uuid.uuid4()
    first = _intent(
        wren,
        CommunicateAction(
            character_id=wren,
            snapshot_id=snapshot,
            target_character_id=sage,
            topic="the pass",
        ),
        snapshot,
    )
    second = _intent(
        ash,
        CommunicateAction(
            character_id=ash,
            snapshot_id=snapshot,
            target_character_id=sage,
            topic="the pass",
        ),
        snapshot,
    )
    # Same target from different locations: one scene, not two.
    scenes = _assemble([first, second], view, snapshot)
    assert len(scenes) == 1


def test_unrelated_intents_stay_apart() -> None:
    wid, hearth, market, wren, ash = _world()
    view = _view(wid, hearth, market, wren, ash)
    snapshot = uuid.uuid4()
    rest = _intent(wren, RestAction(character_id=wren, snapshot_id=snapshot), snapshot)
    wait = _intent(ash, WaitAction(character_id=ash, snapshot_id=snapshot), snapshot)
    scenes = _assemble([rest, wait], view, snapshot)
    assert len(scenes) == 2
    assert not scenes_overlap(scenes[0], scenes[1])


def test_shared_desired_effect_links_distant_intents() -> None:
    wid, hearth, market, wren, ash = _world()
    view = _view(wid, hearth, market, wren, ash)
    snapshot = uuid.uuid4()
    effect = DesiredEffect(effect_family="rest", description="share the lantern")
    first = _intent(wren, RestAction(character_id=wren, snapshot_id=snapshot), snapshot, [effect])
    second = _intent(ash, RestAction(character_id=ash, snapshot_id=snapshot), snapshot, [effect])
    scenes = _assemble([first, second], view, snapshot)
    assert len(scenes) == 1
    assert scenes_overlap(scenes[0], scenes[0])


def test_causal_dependency_links_intents() -> None:
    wid, hearth, market, wren, ash = _world()
    view = _view(wid, hearth, market, wren, ash)
    snapshot = uuid.uuid4()
    first = _intent(wren, WaitAction(character_id=wren, snapshot_id=snapshot), snapshot)
    second = _intent(
        ash,
        WaitAction(character_id=ash, snapshot_id=snapshot),
        snapshot,
        [DesiredEffect(effect_family="follow", description="after", depends_on_intent_id=first.id)],
    )
    scenes = _assemble([first, second], view, snapshot)
    assert len(scenes) == 1


def test_grouping_ignores_input_order() -> None:
    wid, hearth, market, wren, ash = _world()
    view = _view(wid, hearth, market, wren, ash)
    snapshot = uuid.uuid4()
    intents = [
        _intent(
            wren,
            CommunicateAction(
                character_id=wren,
                snapshot_id=snapshot,
                target_character_id=ash,
                topic="dawn",
            ),
            snapshot,
        ),
        _intent(ash, WaitAction(character_id=ash, snapshot_id=snapshot), snapshot),
        _intent(wren, RestAction(character_id=wren, snapshot_id=snapshot), snapshot),
    ]
    forward = _assemble(list(intents), view, snapshot)
    backward = _assemble(list(reversed(intents)), view, snapshot)
    assert [s.id for s in forward] == [s.id for s in backward]
    assert [s.intent_ids for s in forward] == [s.intent_ids for s in backward]


def test_communicate_target_joins_as_reactor() -> None:
    wid, hearth, market, wren, ash = _world()
    view = _view(wid, hearth, market, wren, ash)
    snapshot = uuid.uuid4()
    talk = _intent(
        wren,
        CommunicateAction(
            character_id=wren,
            snapshot_id=snapshot,
            target_character_id=ash,
            topic="dawn",
        ),
        snapshot,
    )
    scenes = _assemble([talk], view, snapshot)
    assert len(scenes) == 1
    roles = {p.character_id: p.role for p in scenes[0].participants}
    assert roles == {wren: ParticipantRole.INITIATOR, ash: ParticipantRole.REACTOR}
    assert f"character:{ash}" in scenes[0].mutable_aggregate_ids


def test_read_only_intents_have_no_aggregates() -> None:
    _wid, _hearth, _market, _wren, ash = _world()
    snapshot = uuid.uuid4()
    wait = _intent(ash, WaitAction(character_id=ash, snapshot_id=snapshot), snapshot)
    assert mutable_aggregates(wait) == frozenset()
