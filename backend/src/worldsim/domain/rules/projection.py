"""Pure effect projectors (owned by S0-SIM-001).

Each projector takes a frozen state plus one validated effect and returns
the next state with a bumped version. Out-of-bounds results raise instead
of clamping: validated plans never produce them.
"""

from __future__ import annotations

from worldsim.domain.characters import Character
from worldsim.domain.effects import (
    AdvanceClockEffect,
    DomainEffect,
    MoveEntityEffect,
    ResourceAdjustedEffect,
)
from worldsim.domain.enums import ResourceKind
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.time import split_absolute
from worldsim.domain.world import World


def apply_character_effect(character: Character, effect: DomainEffect) -> Character:
    if isinstance(effect, MoveEntityEffect):
        return character.model_copy(
            update={"location_id": effect.to_location_id, "version": character.version + 1}
        )
    if isinstance(effect, ResourceAdjustedEffect):
        current = character.stamina if effect.resource is ResourceKind.STAMINA else character.mana
        rested = current + effect.delta
        if not 0 <= rested <= 100:
            raise DomainError(
                ErrorCode.INVARIANT_VIOLATED,
                f"projection left bounds: {effect.resource.value}={rested}",
                {"resource": effect.resource.value, "value": rested},
            )
        field = "stamina" if effect.resource is ResourceKind.STAMINA else "mana"
        return character.model_copy(update={field: rested, "version": character.version + 1})
    return character


def apply_world_effect(world: World, effect: AdvanceClockEffect) -> World:
    day, phase = split_absolute(effect.to_index)
    return world.model_copy(update={"day": day, "phase": phase, "version": world.version + 1})
