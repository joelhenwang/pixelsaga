"""Combat rolls, damage, healing, and level previews (owned by DND-PORT).

Port of rollAttack/rollSave/applyDamage/heal/levelUpPreview. Two
deliberate deviations from perchance-ver/dnd.js, both covered by tests:

- The monolith's crit-damage path crashes (``attack.critDice`` is never
  defined). Crits here roll double dice per the standard 5e rule.
- Damage functions are pure: they take current HP and return the new
  total plus the delta instead of mutating a sheet in place.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from worldsim.domain.rules.dnd.core import prof_bonus
from worldsim.domain.rules.dnd.data import (
    DataTables,
    dict_field,
    entry,
    int_field,
    list_field,
    table,
)
from worldsim.domain.rules.dnd.dice import js_round, parse_dice, roll_d20, roll_dice
from worldsim.domain.rules.dnd.sheets import Sheet, sheet_mod


class AttackRoll(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nat: int
    total: int
    nat20: bool
    nat1: bool
    hit: bool
    crit: bool


class SaveRoll(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nat: int
    total: int
    nat20: bool
    nat1: bool
    success: bool


def roll_attack(
    attack_bonus: int, target_ac: int, rng: Callable[[], float] | None = None
) -> AttackRoll:
    """d20 attack; nat 20 always hits and crits, nat 1 always misses."""
    nat = roll_d20(rng)
    total = nat + (attack_bonus or 0)
    nat20 = nat == 20
    nat1 = nat == 1
    return AttackRoll(
        nat=nat,
        total=total,
        nat20=nat20,
        nat1=nat1,
        hit=nat20 or (not nat1 and total >= target_ac),
        crit=nat20,
    )


def roll_save(bonus: int, dc: int, rng: Callable[[], float] | None = None) -> SaveRoll:
    """d20 save; nat 20 always succeeds, nat 1 always fails."""
    nat = roll_d20(rng)
    total = nat + (bonus or 0)
    nat20 = nat == 20
    nat1 = nat == 1
    return SaveRoll(
        nat=nat,
        total=total,
        nat20=nat20,
        nat1=nat1,
        success=nat20 or (not nat1 and total >= dc),
    )


def crit_damage_dice(dice_text: str | None) -> str | None:
    """Double the dice count for a crit (``1d8`` -> ``2d8``); mods stay single."""
    parsed = parse_dice(dice_text)
    if parsed is None:
        return dice_text
    mod = f"+{parsed.mod}" if parsed.mod > 0 else (str(parsed.mod) if parsed.mod < 0 else "")
    return f"{parsed.count * 2}d{parsed.sides}{mod}"


def roll_damage(
    dice_text: str | None,
    rng: Callable[[], float] | None = None,
    crit: bool = False,
) -> int:
    """Roll damage dice, doubling the dice on a crit."""
    text = crit_damage_dice(dice_text) if crit else dice_text
    return roll_dice(text, rng)


def apply_damage(current: int, maximum: int, amount: float | None) -> tuple[int, int]:
    """Apply damage; returns ``(new_current, dealt)``, floored at zero."""
    dealt = max(0, js_round(amount or 0))
    new_current = max(0, current - dealt)
    return new_current, current - new_current


def heal(current: int, maximum: int, amount: float | None) -> tuple[int, int]:
    """Restore HP; returns ``(new_current, restored)``, capped at max."""
    restored = max(0, js_round(amount or 0))
    new_current = min(maximum, current + restored)
    return new_current, new_current - current


class LevelPreview(BaseModel):
    """Level-up deltas. Never mutates the sheet."""

    model_config = ConfigDict(extra="forbid")

    new_level: int
    hp_gain: int
    prof_bonus: int
    prof_changed: bool
    ability_score_bonus: int
    features: list[str] = []
    cantrips_known: int | None = None
    spells_known: int | None = None
    slots: list[int] | None = None
    class_specific: dict[str, Any] = {}


def level_up_preview(sheet: Sheet, data: DataTables) -> LevelPreview | None:
    """Preview the next level; ``None`` at the level-20 cap."""
    level = sheet.level or 1
    if level >= 20:
        return None
    new_level = level + 1
    class_entry = entry(table(data, "classes"), sheet.character_class)
    tiers = list_field(class_entry, "levels")
    tier = tiers[new_level - 1] if len(tiers) >= new_level else None
    prev = tiers[level - 1] if len(tiers) >= level else None
    tier_row = cast("dict[str, Any]", tier) if isinstance(tier, dict) else {}
    prev_row = cast("dict[str, Any]", prev) if isinstance(prev, dict) else {}
    die = int_field(class_entry, "hit_die", 8)
    tier_casting = dict_field(tier_row, "spellcasting")
    prev_casting = dict_field(prev_row, "spellcasting")
    active = tier_casting or prev_casting
    cantrips_raw = active.get("cantrips_known")
    spells_raw = active.get("spells_known")
    slots = list_field(tier_casting, "slots")
    return LevelPreview(
        new_level=new_level,
        hp_gain=die // 2 + 1 + sheet_mod(sheet, "con"),
        prof_bonus=prof_bonus(new_level),
        prof_changed=prof_bonus(new_level) != prof_bonus(level),
        ability_score_bonus=int_field(tier_row, "ability_score_bonuses"),
        features=[str(item) for item in list_field(tier_row, "features")],
        cantrips_known=cantrips_raw if isinstance(cantrips_raw, int) else None,
        spells_known=spells_raw if isinstance(spells_raw, int) else None,
        slots=[int(item) for item in slots] if slots else None,
        class_specific=dict_field(tier_row, "class_specific"),
    )
