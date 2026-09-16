"""Companion auto-build and recruitment (owned by DND-WIRE).

Port of the monolith's inline companion builder (``dndAutoSheet``,
``dndAutoSpells``, ``dndSpellLimits``) and the ``RECRUIT[name]: desc``
tag handling. Deterministic: the same recruit description always
produces the same sheet. Score ties keep class-list order (both sorts
are stable), including the monolith's flat ``20`` for heal spells
(``averageDice`` of a missing ``.dice`` field is 0).
"""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any, cast

from worldsim.domain.rules.dnd.core import ability_mod, find_entry
from worldsim.domain.rules.dnd.data import (
    DataTables,
    dict_field,
    entry,
    int_field,
    list_field,
    str_field,
    table,
)
from worldsim.domain.rules.dnd.dice import average_dice
from worldsim.domain.rules.dnd.sheets import Sheet, ensure_hp, max_hp, race_ability_bonuses

STAT_ARRAY = [15, 14, 13, 12, 10, 8]
MAX_PARTY_SIZE = 4

ABILITY_PRIORITY: dict[str, list[str]] = {
    "barbarian": ["str", "con", "dex", "wis", "cha", "int"],
    "bard": ["cha", "dex", "con", "int", "wis", "str"],
    "cleric": ["wis", "str", "con", "cha", "dex", "int"],
    "druid": ["wis", "con", "dex", "int", "cha", "str"],
    "fighter": ["str", "con", "dex", "wis", "cha", "int"],
    "monk": ["dex", "wis", "con", "str", "int", "cha"],
    "paladin": ["str", "cha", "con", "wis", "dex", "int"],
    "ranger": ["dex", "wis", "con", "str", "int", "cha"],
    "rogue": ["dex", "int", "con", "wis", "cha", "str"],
    "sorcerer": ["cha", "con", "dex", "int", "wis", "str"],
    "warlock": ["cha", "con", "dex", "wis", "int", "str"],
    "wizard": ["int", "dex", "con", "wis", "cha", "str"],
}
AUTO_WEAPONS: dict[str, list[str]] = {
    "barbarian": ["greataxe", "handaxe"],
    "bard": ["rapier", "dagger"],
    "cleric": ["mace", "spear"],
    "druid": ["quarterstaff", "sling"],
    "fighter": ["longsword", "handaxe"],
    "monk": ["shortsword", "quarterstaff"],
    "paladin": ["longsword", "spear"],
    "ranger": ["longsword", "longbow"],
    "rogue": ["rapier", "shortbow"],
    "sorcerer": ["quarterstaff", "dagger"],
    "warlock": ["quarterstaff", "dagger"],
    "wizard": ["quarterstaff", "dagger"],
}
AUTO_ARMOR: dict[str, str | None] = {
    "cleric": "chain-mail",
    "fighter": "chain-mail",
    "paladin": "chain-mail",
    "ranger": "leather-armor",
    "rogue": "leather-armor",
    "bard": "leather-armor",
    "druid": "leather-armor",
    "barbarian": None,
    "monk": None,
    "sorcerer": None,
    "warlock": None,
    "wizard": None,
}


class SpellLimits:
    """Spell budget for one class/level: pool, caps, highest slot."""

    def __init__(self, pool: list[str], max_cantrips: int, max_known: int, max_slot: int) -> None:
        self.pool = pool
        self.max_cantrips = max_cantrips
        self.max_known = max_known
        self.max_slot = max_slot


def spell_limits(
    data: DataTables, class_key: str, level: int, stats: dict[str, int]
) -> SpellLimits:
    """Eligible spell pool and pick caps for a class at a level."""
    classes = table(data, "classes")
    cls = entry(classes, class_key)
    pool = list_field(cls, "spells")
    if not cls or not pool:
        return SpellLimits([], 0, 0, 0)
    clamped = min(max(level, 1), 20) - 1
    tiers = list_field(cls, "levels")
    raw_tier = tiers[clamped] if len(tiers) > clamped else None
    tier_row = cast("dict[str, Any]", raw_tier) if isinstance(raw_tier, dict) else {}
    casting = dict_field(tier_row, "spellcasting")
    slots = list_field(casting, "slots")
    max_slot = 0
    for pos, count in enumerate(slots):
        if isinstance(count, int) and count > 0:
            max_slot = pos + 1
    max_cantrips = int_field(casting, "cantrips_known")
    known_raw = casting.get("spells_known")
    max_known: int | None = known_raw if isinstance(known_raw, int) else None
    if max_known is None:
        class_casting = dict_field(cls, "spellcasting")
        ability = str_field(class_casting, "ability")
        if ability:
            mod = ability_mod(stats.get(ability, 10))
            max_known = max(1, mod + level)
    spells = table(data, "spells")
    eligible = [
        index
        for index in pool
        if (row := entry(spells, str(index)))
        and (int_field(row, "level") == 0 or 1 <= int_field(row, "level") <= max_slot)
    ]
    return SpellLimits(eligible, max_cantrips, max_known or 0, max_slot)


def _spell_score(data: DataTables, index: str) -> float:
    row = entry(table(data, "spells"), index)
    level = int_field(row, "level")
    damage = dict_field(row, "damage")
    if level == 0:
        tiers = dict_field(damage, "atCharacterLevel")
        dice = str_field(tiers, "1") or str_field(damage, "base")
        return 10 + average_dice(dice) if dice else 0
    score = 0.0
    if dict_field(row, "heal"):
        score = 20 + average_dice(None)
    if damage:
        slots = dict_field(damage, "atSlotLevel")
        dice = str_field(slots, str(level)) or str_field(damage, "base")
        if dice:
            score += 15 + average_dice(dice) + level * 3
    return score + level


def auto_spells(data: DataTables, class_key: str, level: int, stats: dict[str, int]) -> list[str]:
    """Best-scoring spell picks within the class budget."""
    limits = spell_limits(data, class_key, level, stats)
    if not limits.pool or limits.max_cantrips + limits.max_known == 0:
        return []
    spells = table(data, "spells")
    cantrips = sorted(
        [i for i in limits.pool if int_field(entry(spells, i), "level") == 0],
        key=lambda i: _spell_score(data, i),
        reverse=True,
    )[: limits.max_cantrips]
    leveled = [i for i in limits.pool if int_field(entry(spells, i), "level") >= 1]
    forced: list[str] = []
    for slot in range(limits.max_slot, 0, -1):
        if len(forced) >= limits.max_known:
            break
        same = [i for i in leveled if int_field(entry(spells, i), "level") == slot]
        if same:
            best = max(same, key=lambda i: _spell_score(data, i))
            forced.append(best)
    rest = sorted(
        [i for i in leveled if i not in forced],
        key=lambda i: _spell_score(data, i),
        reverse=True,
    )
    return (cantrips + forced + rest)[: limits.max_cantrips + limits.max_known]


def first_subclass(data: DataTables, class_key: str) -> str | None:
    """First subclass index for a class, if the tables name one."""
    for key in table(data, "subclasses"):
        row = entry(table(data, "subclasses"), key)
        if str_field(row, "class") == class_key:
            return key
    return None


def auto_sheet(name: str, race: str, class_key: str, level: int, data: DataTables) -> Sheet:
    """Build a full companion sheet from a story identity."""
    priority = ABILITY_PRIORITY.get(class_key, ABILITY_PRIORITY["fighter"])
    stats = {ability: STAT_ARRAY[pos] for pos, ability in enumerate(priority)}
    weapons = table(data, "weapons")
    return _finish_sheet(name, race, class_key, level, stats, weapons, data)


def _finish_sheet(
    name: str,
    race: str,
    class_key: str,
    level: int,
    stats: dict[str, int],
    weapons: dict[str, Any],
    data: DataTables,
) -> Sheet:
    for ability, bonus in race_ability_bonuses(data, race).items():
        stats[ability] = stats.get(ability, 0) + bonus
    base_ac: int | None = None
    if class_key == "monk" and not AUTO_ARMOR.get(class_key):
        base_ac = 10 + ability_mod(stats.get("wis", 10))
    if class_key == "barbarian" and not AUTO_ARMOR.get(class_key):
        base_ac = 10 + ability_mod(stats.get("con", 10))
    armor = AUTO_ARMOR.get(class_key)
    picked = [w for w in AUTO_WEAPONS.get(class_key, []) if w in weapons][:2]
    sheet = Sheet(
        name=name,
        race=race,
        character_class=class_key,
        subclass=first_subclass(data, class_key),
        level=level,
        stats=stats,
        armor=armor,
        shield=class_key in ("cleric", "fighter", "paladin", "barbarian"),
        base_ac=base_ac,
        weapons=picked,
        spells=auto_spells(data, class_key, level, stats),
    )
    ensure_hp(sheet, max_hp(data, sheet))
    return sheet


def recruit_sheet(name: str, desc: str, party_levels: list[int], data: DataTables) -> Sheet:
    """Resolve a ``RECRUIT[name]: desc`` tag to a built sheet.

    Class and race fuzzy-match the description (fighter/human fallbacks);
    the level parses from ``level N`` clamped to the party max + 1.
    The monolith also consults the NPC's established physical race here;
    backend characters carry no race, so an unnamed race is human.
    """
    text = desc or ""
    match = re.search(r"level\s+(\d+)", text, re.IGNORECASE)
    party_max = max(party_levels) if party_levels else 1
    if match:
        level = min(max(int(match.group(1)), 1), party_max + 1)
    else:
        level = party_max
    class_hit = find_entry(table(data, "classes"), text)
    class_key = class_hit.index if class_hit else "fighter"
    race_hit = find_entry(table(data, "races"), text)
    race = race_hit.index if race_hit else "human"
    return auto_sheet(name, race, class_key, level, data)


def dnd_party_prompt(members: list[Sheet], data: DataTables) -> str:
    """Party block for the narrator prompt; empty with no members."""
    from worldsim.domain.rules.dnd.sheets import build_sheet_summary

    if not members:
        return ""
    lines = [
        f"- D&D PARTY (real 5e sheets \u2014 the ENGINE resolves all rolls, "
        "damage, HP, and spells; you describe actions, never numbers). "
        f"The party is EXACTLY the {len(members)} member(s) listed below "
        "\u2014 do not invent extra party members; companions only join "
        "when the story has them join the party:"
    ]
    for sheet in members:
        for line in build_sheet_summary(data, sheet).split("\n"):
            lines.append("  " + line)
    return "\n" + "\n".join(lines)


RULES_PROMPT_VERSION = "dnd-rules.v1"


@functools.cache
def dnd_rules_text() -> str:
    """DM instructions for D&D mode, verbatim from the monolith prompt."""
    path = Path(__file__).resolve().parents[5] / "prompts" / f"{RULES_PROMPT_VERSION}.md"
    return path.read_text(encoding="utf-8")
