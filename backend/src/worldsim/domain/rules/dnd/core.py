"""Abilities, lookup, XP, and encounter math (owned by DND-PORT).

Pure port of the matching perchance-ver/dnd.js helpers. Table values
are the standard 5e advancement/encounter figures the monolith carries
inline; fuzzy ``find_entry`` keeps the monolith's candidate order and
shortest-name tiebreak exactly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from worldsim.domain.rules.dnd.data import entry, int_field, str_field, table
from worldsim.domain.rules.dnd.dice import js_round

ABILITY_KEYS = ["str", "dex", "con", "int", "wis", "cha"]
ABILITY_FULL = {
    "str": "Strength",
    "dex": "Dexterity",
    "con": "Constitution",
    "int": "Intelligence",
    "wis": "Wisdom",
    "cha": "Charisma",
}

# Player XP thresholds by level (index 0 = level 1).
LEVEL_XP = [
    0,
    300,
    900,
    2700,
    6500,
    14000,
    23000,
    34000,
    48000,
    64000,
    85000,
    100000,
    120000,
    140000,
    165000,
    195000,
    225000,
    265000,
    305000,
    355000,
]
# Encounter XP budget per character by party level (easy/medium/hard/deadly).
ENCOUNTER_BUDGET = [
    [25, 50, 75, 100],
    [50, 100, 150, 200],
    [75, 150, 225, 400],
    [125, 250, 375, 500],
    [250, 500, 750, 1100],
    [300, 600, 900, 1400],
    [350, 750, 1100, 1700],
    [450, 900, 1400, 2100],
    [550, 1100, 1600, 2400],
    [600, 1200, 1900, 2800],
    [800, 1600, 2400, 3600],
    [1000, 2000, 3000, 4500],
    [1100, 2200, 3400, 5100],
    [1250, 2500, 3800, 5700],
    [1400, 2800, 4300, 6400],
    [1600, 3200, 4800, 7200],
    [2000, 3900, 5900, 8800],
    [2100, 4200, 6300, 9500],
    [2400, 4900, 7300, 10900],
    [2800, 5700, 8500, 12700],
]
ENCOUNTER_MULT = [
    (1, 1),
    (2, 1.5),
    (3, 2),
    (6, 2),
    (7, 2.5),
    (10, 2.5),
    (11, 3),
    (14, 3),
    (15, 4),
    (float("inf"), 4),
]
TIERS = ["easy", "medium", "hard", "deadly"]

_IRREGULAR_PLURALS = {"wolves": "wolf", "elves": "elf", "dwarves": "dwarf"}
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_DASH_RUN_RE = re.compile(r"-+")


def ability_mod(score: int) -> int:
    return (score - 10) // 2


def prof_bonus(level: int) -> int:
    return 2 + (max(1, level) - 1) // 4


def fmt_mod(value: int) -> str:
    return f"+{value}" if value > 0 else str(value)


def slugify(text: str | None) -> str:
    slug = _NON_ALNUM_RE.sub("-", str(text or "").lower())
    return _DASH_RUN_RE.sub("-", slug).strip("-")


def _compact(slug: str | None) -> str | None:
    return slug.replace("-", "") if slug else slug


def _singularize(slug: str) -> str | None:
    parts = slug.split("-")
    last = parts[-1]
    single: str | None = None
    if last in _IRREGULAR_PLURALS:
        single = _IRREGULAR_PLURALS[last]
    elif len(last) > 3 and last.endswith("s"):
        single = last[:-1]
    if not single:
        return None
    parts[-1] = single
    return "-".join(parts)


@dataclass(frozen=True)
class FoundEntry:
    """A data-table hit: storage index plus the raw entry."""

    index: str
    entry: dict[str, Any]


def find_entry(table: dict[str, Any] | None, query: str | None) -> FoundEntry | None:
    """Fuzzy table lookup with the monolith's candidate order.

    Exact slug, compacted slug, singularized forms, then name equality,
    then substring with shortest-name tiebreak. Returns ``None`` on miss.
    """
    if not table or not query:
        return None
    slug = slugify(query)
    if not slug:
        return None
    candidates: list[str] = []
    for cand in (
        slug,
        _compact(slug),
        _singularize(slug),
        _compact(_singularize(slug)),
        _singularize(_compact(slug) or ""),
        _compact(_singularize(_compact(slug) or "")),
    ):
        if cand and cand not in candidates:
            candidates.append(cand)
    for cand in candidates:
        hit = entry(table, cand)
        if hit:
            return FoundEntry(index=cand, entry=hit)
    for index in table:
        row = entry(table, index)
        if not row:
            continue
        name = slugify(str_field(row, "name"))
        packed = _compact(name) or ""
        for cand in candidates:
            if name == cand or packed == cand:
                return FoundEntry(index=index, entry=row)
    best: FoundEntry | None = None
    best_len = 0
    for index in table:
        row = entry(table, index)
        if not row:
            continue
        name = slugify(str_field(row, "name"))
        packed = _compact(name) or ""
        for cand in candidates:
            if cand in name or name in cand or cand in packed or packed in cand:
                if best is None or len(name) < best_len:
                    best = FoundEntry(index=index, entry=row)
                    best_len = len(name)
                break
    return best


def ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    rem = n % 10
    return f"{n}{'st' if rem == 1 else 'nd' if rem == 2 else 'rd' if rem == 3 else 'th'}"


def xp_for_level(level: int) -> int:
    return LEVEL_XP[min(max(1, level), 20) - 1]


def level_from_xp(xp: int) -> int:
    for level in range(20, 0, -1):
        if xp >= LEVEL_XP[level - 1]:
            return level
    return 1


def xp_for_next_level(level: int, xp: int) -> int | None:
    """XP still needed for the next level; ``None`` at the cap."""
    if level >= 20:
        return None
    return LEVEL_XP[level] - xp


@dataclass(frozen=True)
class EncounterXp:
    total_xp: int
    adjusted_xp: int
    multiplier: float
    monster_count: int


@dataclass(frozen=True)
class MonsterRef:
    index: str
    count: int = 1


def encounter_xp(monsters: list[MonsterRef], data: dict[str, dict[str, Any]]) -> EncounterXp:
    """Raw and multiplier-adjusted encounter XP (DMG table)."""
    monsters_table = table(data, "monsters")
    total = 0
    count = 0
    for ref in monsters:
        xp = int_field(entry(monsters_table, ref.index), "xp")
        total += ref.count * xp
        count += ref.count
    mult = 1.0
    for limit, value in ENCOUNTER_MULT:
        if count <= limit:
            mult = float(value)
            break
    return EncounterXp(
        total_xp=total,
        adjusted_xp=js_round(total * mult),
        multiplier=mult,
        monster_count=count,
    )


@dataclass(frozen=True)
class EncounterDifficulty:
    party_level: int
    total_xp: int
    adjusted_xp: int
    multiplier: float
    monster_count: int
    thresholds: dict[str, int]
    difficulty: str


def encounter_difficulty(
    party_levels: list[int],
    monsters: list[MonsterRef],
    data: dict[str, dict[str, Any]],
) -> EncounterDifficulty:
    """Difficulty band for a party against a monster group."""
    xp = encounter_xp(monsters, data)
    party_size = max(1, len(party_levels))
    avg = js_round(sum(party_levels) / party_size) if party_levels else 1
    budget = [value * party_size for value in ENCOUNTER_BUDGET[min(max(1, avg), 20) - 1]]
    difficulty = "trivial"
    thresholds: dict[str, int] = {}
    for tier, value in zip(TIERS, budget, strict=True):
        thresholds[tier] = value
        if xp.adjusted_xp >= value:
            difficulty = tier
    if xp.adjusted_xp >= budget[3] * 1.25:
        difficulty = "overwhelming"
    return EncounterDifficulty(
        party_level=avg,
        total_xp=xp.total_xp,
        adjusted_xp=xp.adjusted_xp,
        multiplier=xp.multiplier,
        monster_count=xp.monster_count,
        thresholds=thresholds,
        difficulty=difficulty,
    )
