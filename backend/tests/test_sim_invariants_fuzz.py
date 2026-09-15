import random

from helpers_sim import make_world_view

from worldsim.domain.commands import MoveAction, RestAction, WaitAction
from worldsim.domain.ids import new_snapshot_id
from worldsim.domain.rules.invariants import violations
from worldsim.domain.rules.projection import apply_character_effect
from worldsim.domain.rules.validation import plan_effects


def test_valid_views_hold_every_invariant() -> None:
    report = violations(make_world_view())
    assert report == {
        "resources_in_bounds": [],
        "locations_known": [],
        "world_membership": [],
    }


def test_seeded_fuzz_finds_only_injected_faults() -> None:
    rng = random.Random(20260915)
    for round_index in range(300):
        stamina = rng.randint(-20, 120)
        mana = rng.randint(-20, 120)
        fault = rng.choice(["none", "location", "world"])
        view = make_world_view()
        wren = view.characters[0].model_copy(update={"stamina": stamina, "mana": mana})
        if fault == "location":
            wren = wren.model_copy(update={"location_id": view.world.id})
        characters = [wren, view.characters[1]]
        if fault == "world":
            characters = [
                wren,
                view.characters[1].model_copy(update={"world_id": view.locations[0].id}),
            ]
        view = view.model_copy(update={"characters": characters})
        report = violations(view)
        expect_resources = not (0 <= stamina <= 100 and 0 <= mana <= 100)
        assert (report["resources_in_bounds"] != []) == expect_resources, round_index
        assert (report["locations_known"] != []) == (fault == "location"), round_index
        assert (report["world_membership"] != []) == (fault == "world"), round_index


def test_planned_effects_preserve_invariants() -> None:
    rng = random.Random(7)
    for _ in range(100):
        view = make_world_view(stamina=rng.randint(20, 100), mana=rng.randint(20, 100))
        wren = view.characters[0]
        snapshot = new_snapshot_id()
        intent = rng.choice(
            [
                WaitAction(character_id=wren.id, snapshot_id=snapshot),
                RestAction(character_id=wren.id, snapshot_id=snapshot),
                MoveAction(
                    character_id=wren.id,
                    snapshot_id=snapshot,
                    destination_location_id=view.locations[1].id,
                    route_id=view.locations[0].routes[0].id,
                ),
            ]
        )
        moved = wren
        for effect in plan_effects(intent, view):
            moved = apply_character_effect(moved, effect)
        assert moved.location_id in {place.id for place in view.locations}
        assert 0 <= moved.stamina <= 100
        assert 0 <= moved.mana <= 100
