"""Adventurer sheets and derived statistics (owned by DND-PORT).

Port of createSheet/sheetMod/sheetProf/armorAC/maxHp/ensureHp and the
spell-list helpers from perchance-ver/dnd.js. Two monolith quirks are
kept deliberately and covered by tests: a named-but-missing armor
entry grants no Dex bonus at all, and a negative attack bonus renders
as ``+-1`` in summaries.
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.rules.dnd.core import (
    ability_mod,
    find_entry,
    fmt_mod,
    ordinal,
    prof_bonus,
)
from worldsim.domain.rules.dnd.data import (
    DataTables,
    dict_field,
    entry,
    int_field,
    list_field,
    str_field,
    table,
)


class HitPoints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current: int
    max: int


class Sheet(BaseModel):
    """One adventurer. Mirrors the monolith's sheet object field for field."""

    model_config = ConfigDict(extra="forbid")

    name: str = "Adventurer"
    race: str | None = None
    character_class: str = "fighter"
    subclass: str | None = None
    background: str | None = None
    level: int = 1
    stats: dict[str, int] = Field(
        default_factory=lambda: {
            "str": 10,
            "dex": 10,
            "con": 10,
            "int": 10,
            "wis": 10,
            "cha": 10,
        }
    )
    hp: HitPoints | None = None
    armor: str | None = None
    shield: bool = False
    base_ac: int | None = None
    weapons: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    spells: list[str] = Field(default_factory=list)
    prepared: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    xp: int = 0


def sheet_mod(sheet: Sheet, ability: str) -> int:
    return ability_mod(sheet.stats.get(ability, 10))


def sheet_prof(sheet: Sheet) -> int:
    return prof_bonus(sheet.level or 1)


def _class_entry(data: DataTables, sheet: Sheet) -> dict[str, Any]:
    return entry(table(data, "classes"), sheet.character_class)


def spellcasting_ability(data: DataTables, sheet: Sheet) -> str | None:
    casting = dict_field(_class_entry(data, sheet), "spellcasting")
    return str_field(casting, "ability")


def spell_dc(data: DataTables, sheet: Sheet) -> int | None:
    ability = spellcasting_ability(data, sheet)
    if ability is None:
        return None
    return 8 + sheet_prof(sheet) + sheet_mod(sheet, ability)


def spell_attack_bonus(data: DataTables, sheet: Sheet) -> int | None:
    ability = spellcasting_ability(data, sheet)
    if ability is None:
        return None
    return sheet_prof(sheet) + sheet_mod(sheet, ability)


def weapon_attack_bonus(data: DataTables, sheet: Sheet, weapon: dict[str, Any]) -> int:
    _ = data
    bonus = sheet_prof(sheet)
    props = list_field(weapon, "properties")
    if str_field(weapon, "weapon_range") == "Ranged":
        return bonus + ability_mod(sheet.stats.get("dex", 10))
    if "finesse" in props:
        return bonus + max(
            ability_mod(sheet.stats.get("str", 10)),
            ability_mod(sheet.stats.get("dex", 10)),
        )
    return bonus + ability_mod(sheet.stats.get("str", 10))


def armor_ac(data: DataTables, sheet: Sheet) -> int:
    """Armor class. Missing-but-named armor skips Dex entirely (kept quirk)."""
    armor = sheet.base_ac or 10
    dex = ability_mod(sheet.stats.get("dex", 10))
    armor_table = table(data, "armor")
    if sheet.armor:
        found = find_entry(armor_table, sheet.armor)
        worn = found.entry if found else {}
        ac = dict_field(worn, "ac")
        if ac:
            if str_field(worn, "armor_category") == "Shield":
                armor = int_field(ac, "base", armor)
            else:
                armor = int_field(ac, "base", armor)
                if ac.get("dex_bonus"):
                    cap = ac.get("max_bonus")
                    capped = dex if cap is None else min(dex, int_field(ac, "max_bonus", dex))
                    armor += max(0, capped)

    else:
        armor += dex
    if sheet.shield:
        shield_hit = find_entry(armor_table, "shield")
        shield_ac = dict_field(shield_hit.entry if shield_hit else {}, "ac")
        armor += int_field(shield_ac, "base", 0)
    return armor


def max_hp(data: DataTables, sheet: Sheet) -> int:
    """Preset max wins; otherwise average HP per the monolith's formula."""
    if sheet.hp is not None:
        return sheet.hp.max
    die = int_field(_class_entry(data, sheet), "hit_die", 8)
    con = sheet_mod(sheet, "con")
    average = die // 2 + 1
    return die + con + (max(1, sheet.level or 1) - 1) * (average + con)


def ensure_hp(sheet: Sheet, maximum: int) -> HitPoints:
    """Fill missing HP; never touch a live current value."""
    if sheet.hp is None:
        sheet.hp = HitPoints(current=maximum, max=maximum)
    else:
        sheet.hp.max = maximum
    return sheet.hp


def class_spell_list(data: DataTables, sheet: Sheet) -> list[str]:
    return [str(item) for item in list_field(_class_entry(data, sheet), "spells")]


def known_spells(sheet: Sheet) -> list[str]:
    return list(sheet.spells)


def race_ability_bonuses(data: DataTables, race_index: str) -> dict[str, int]:
    total: dict[str, int] = {}
    for grant in list_field(entry(table(data, "races"), race_index), "ability_bonuses"):
        if not isinstance(grant, dict):
            continue
        row = cast("dict[str, Any]", grant)
        ability = str_field(row, "ability")
        bonus = row.get("bonus", 0)
        if ability is not None and isinstance(bonus, int) and not isinstance(bonus, bool):
            total[ability] = total.get(ability, 0) + bonus
    return total


def _spell_line(spells: dict[str, Any], index: str) -> str:
    row = entry(spells, index)
    if not row:
        return index
    name = str_field(row, "name") or index
    level = int_field(row, "level")
    damage = dict_field(row, "damage")
    detail = ""
    if level == 0 and damage:
        tiers = dict_field(damage, "atCharacterLevel")
        first = str_field(tiers, "1")
        if first:
            detail = f" ({first} {str_field(damage, 'type')})"
        return f"{name} (cantrip){detail}"
    if damage and str_field(damage, "base"):
        detail = f" ({str_field(damage, 'base')} {str_field(damage, 'type')})"
    return f"{name} ({ordinal(level)}){detail}"


def build_sheet_summary(data: DataTables, sheet: Sheet) -> str:
    """Exact ``[D&D SHEET]`` text the monolith feeds the narrator."""
    lines = [
        f"[D&D SHEET] {sheet.name} - Level {sheet.level} "
        f"{sheet.race or '?'} {sheet.character_class or '?'}"
        + (f" ({sheet.subclass})" if sheet.subclass else "")
    ]
    maximum = max_hp(data, sheet)
    current = sheet.hp.current if sheet.hp else maximum
    lines.append(f"HP {current}/{maximum}, AC {armor_ac(data, sheet)}, Prof +{sheet_prof(sheet)}")
    mods = " ".join(
        f"{key.upper()} {fmt_mod(sheet_mod(sheet, key))}"
        for key in ("str", "dex", "con", "int", "wis", "cha")
    )
    lines.append(mods)
    dc = spell_dc(data, sheet)
    if dc is not None:
        lines.append(f"Spell DC {dc}, spell attack +{spell_attack_bonus(data, sheet)}")
    spell_table = table(data, "spells")
    if sheet.spells:
        lines.append("Spells: " + ", ".join(_spell_line(spell_table, i) for i in sheet.spells))
    if sheet.conditions:
        lines.append("Conditions: " + ", ".join(sheet.conditions))
    weapon_table = table(data, "weapons")
    if sheet.weapons:
        parts: list[str] = []
        for index in sheet.weapons:
            raw = entry(weapon_table, index)
            if not raw:
                parts.append(index)
                continue
            damage = dict_field(raw, "damage")
            dice = (
                f"{str_field(damage, 'dice') or ''} {str_field(damage, 'type') or ''}".strip()
                if damage
                else ""
            )
            attack = weapon_attack_bonus(data, sheet, raw)
            parts.append(f"{str_field(raw, 'name') or index} +{attack} ({dice})")
        lines.append("Weapons: " + ", ".join(parts))
    return "\n".join(lines)
