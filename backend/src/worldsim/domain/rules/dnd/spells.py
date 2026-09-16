"""Spell resolution and description (owned by DND-PORT).

Port of resolveSpell/describeSpell: cantrip dice scale by character
level tiers, leveled spells by expended slot, save DCs come from the
caster's sheet.
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.rules.dnd.data import (
    DataTables,
    dict_field,
    entry,
    int_field,
    list_field,
    str_field,
    table,
)
from worldsim.domain.rules.dnd.sheets import Sheet, spell_dc


class SpellSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    success: str | None = None
    dc_value: int | None = None


class SpellDamage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dice: str
    kind: str | None = None
    slot_level: int | None = None


class ResolvedSpell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    index: str
    level: int
    school: str | None = None
    casting_time: str | None = None
    range: str | None = None
    components: list[str] = Field(default_factory=list)
    material: str | None = None
    duration: str | None = None
    concentration: bool = False
    ritual: bool = False
    attack_type: str | None = None
    dc: SpellSave | None = None
    aoe: Any = None
    heal: Any = None
    heal_dice: str | None = None
    damage: SpellDamage | None = None
    classes: list[str] = Field(default_factory=list)


def resolve_spell(
    index: str, sheet: Sheet, data: DataTables, slot_level: int | None = None
) -> ResolvedSpell | None:
    """Resolve a spell index to cast-time details; ``None`` on miss."""
    row = entry(table(data, "spells"), index)
    if not row:
        return None
    level = int_field(row, "level")
    damage: SpellDamage | None = None
    slot: int | None = None
    spec = dict_field(row, "damage")
    damage_kind = str_field(spec, "type")
    if spec:
        if level == 0:
            tiers = dict_field(spec, "atCharacterLevel")
            tier = "1"
            if tiers:
                for key in sorted(tiers, key=int):
                    if int(key) <= (sheet.level or 1):
                        tier = key
                dice = str_field(tiers, tier) or str_field(spec, "base")
            else:
                dice = str_field(spec, "base")
            if dice is not None:
                damage = SpellDamage(dice=dice, kind=damage_kind)
        else:
            slot = max(level, slot_level or level)
            slots = dict_field(spec, "atSlotLevel")
            dice = str_field(slots, str(slot)) or str_field(spec, "base")
            if dice is not None:
                damage = SpellDamage(dice=dice, kind=damage_kind, slot_level=slot)
    save: SpellSave | None = None
    dc_spec = dict_field(row, "dc")
    if dc_spec:
        save = SpellSave(
            kind=str_field(dc_spec, "type") or "",
            success=str_field(dc_spec, "success"),
            dc_value=spell_dc(data, sheet),
        )
    raw_heal = row.get("heal")
    heal_dice: str | None = None
    if isinstance(raw_heal, dict):
        # Slot-keyed table ("1": "1d8 + MOD"); the monolith printed
        # "heals undefined" here because it read a .dice field that
        # never exists. MOD stays literal for the narrator to fill.
        heal_table = cast("dict[str, Any]", raw_heal)
        slot_key = str(slot if slot is not None else level)
        heal_dice = str_field(heal_table, slot_key)
    return ResolvedSpell(
        name=str_field(row, "name") or index,
        index=index,
        level=level,
        school=str_field(row, "school"),
        casting_time=str_field(row, "casting_time"),
        range=str_field(row, "range"),
        components=[str(item) for item in list_field(row, "components")],
        material=str_field(row, "material"),
        duration=str_field(row, "duration"),
        concentration=bool(row.get("concentration", False)),
        ritual=bool(row.get("ritual", False)),
        attack_type=str_field(row, "attack_type"),
        dc=save,
        aoe=row.get("aoe"),
        heal=raw_heal,
        heal_dice=heal_dice,
        damage=damage,
        classes=[str(item) for item in list_field(row, "classes")],
    )


def describe_spell(resolved: ResolvedSpell | None) -> str | None:
    """One-line cast summary for prompts; ``None`` for no spell."""
    if resolved is None:
        return None
    parts = [resolved.name]
    if resolved.damage:
        parts.append(f"{resolved.damage.dice} {resolved.damage.kind} damage")
    if resolved.dc:
        parts.append(f"DC {resolved.dc.dc_value} {resolved.dc.kind} save ({resolved.dc.success})")
    if resolved.attack_type:
        parts.append("spell attack vs AC")
    if resolved.heal_dice:
        parts.append(f"heals {resolved.heal_dice}")
    if resolved.concentration:
        parts.append("concentration")
    if resolved.range:
        parts.append(resolved.range)
    return ", ".join(parts)
