"""Party builder parity with the monolith inline script (owned by DND-WIRE).

Vectors in ``fixtures/dnd_party_vectors.json`` come from the actual
``dndAutoSheet``/``dndAutoSpells``/``dndSpellLimits`` functions in
``perchance-ver/index.html`` via ``scripts/gen_dnd_party_vectors.mjs``.
Recruit-level behavior (name cap, idempotency) lives with the command
layer; only the pure sheet resolution is pinned here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldsim.domain.rules.dnd import (
    ABILITY_PRIORITY,
    AUTO_ARMOR,
    AUTO_WEAPONS,
    MAX_PARTY_SIZE,
    STAT_ARRAY,
    auto_sheet,
    auto_spells,
    dnd_party_prompt,
    dnd_rules_text,
    load_data,
    parse_recruit_tags,
    recruit_sheet,
    spell_limits,
)

ROOT = Path(__file__).parent.parent.parent
DATA = load_data(ROOT / "content" / "dnd")
VECTORS: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "dnd_party_vectors.json").read_text(encoding="utf-8")
)

BASE_STATS = {"str": 10, "dex": 14, "con": 12, "int": 10, "wis": 10, "cha": 8}


def test_builder_tables_match() -> None:
    tables = VECTORS["tables"]
    assert STAT_ARRAY == tables["statArray"]
    assert ABILITY_PRIORITY == tables["priorities"]
    assert AUTO_WEAPONS == tables["autoWeapons"]
    assert AUTO_ARMOR == tables["autoArmor"]
    assert MAX_PARTY_SIZE == tables["maxParty"] == 4


def test_spell_limits_vectors() -> None:
    cases = {"wizard1": ("wizard", 1), "wizard5": ("wizard", 5), "cleric3": ("cleric", 3)}
    for key, (cls, level) in cases.items():
        want = VECTORS["limits"][f"{cls}{level}"]
        got = spell_limits(DATA, cls, level, dict(BASE_STATS))
        assert got.pool == want["list"], key
        assert got.max_cantrips == want["maxCantrips"], key
        assert got.max_known == want["maxKnown"], key
        assert got.max_slot == want["maxSlot"], key
    martial = spell_limits(DATA, "fighter", 3, dict(BASE_STATS))
    assert (martial.pool, martial.max_known, martial.max_slot) == ([], 0, 0)


def test_auto_spells_vectors() -> None:
    for key in ("wizard5", "cleric3", "bard2", "sorcerer4"):
        cls, level = key.rstrip("0123456789"), int(key[-1])
        assert auto_spells(DATA, cls, level, dict(BASE_STATS)) == VECTORS["autoSpells"][key], key
    assert auto_spells(DATA, "fighter", 3, dict(BASE_STATS)) == []


def test_auto_sheet_vectors() -> None:
    for key, (name, race, cls, level) in {
        "Lyra-ranger3": ("Lyra", "elf", "ranger", 3),
        "Borin-fighter1": ("Borin", "dwarf", "fighter", 1),
        "Elara-wizard5": ("Elara", "human", "wizard", 5),
        "Thrak-barbarian2": ("Thrak", "half-orc", "barbarian", 2),
        "Mira-cleric4": ("Mira", "halfling", "cleric", 4),
    }.items():
        want = VECTORS["autoSheet"][key]
        got = auto_sheet(name, race, cls, level, DATA)
        assert got.stats == want["stats"], key
        assert got.armor == want["armor"], key
        assert got.shield == want["shield"], key
        assert got.base_ac == want["baseAc"], key
        assert got.weapons == want["weapons"], key
        assert got.spells == want["spells"], key
        assert got.hp is not None and got.hp.model_dump() == want["hp"], key
        assert got.subclass == want["subclass"], key


def test_recruit_sheet_resolution() -> None:
    sheet = recruit_sheet("Lyra", "elf ranger, level 3", [3, 3], DATA)
    assert (sheet.race, sheet.character_class, sheet.level) == ("elf", "ranger", 3)
    # Level clamps to party max + 1; unknown class falls back to fighter.
    capped = recruit_sheet("Grog", "orc brawler, level 9", [2], DATA)
    assert (capped.level, capped.character_class) == (3, "fighter")
    # No level given: party max. No race named: human.
    plain = recruit_sheet("Ash", "a traveling bard", [4], DATA)
    assert (plain.level, plain.race, plain.character_class) == (4, "human", "bard")
    # Deterministic: same input, same sheet.
    assert recruit_sheet("Lyra", "elf ranger, level 3", [3, 3], DATA) == sheet


def test_recruit_tag_scan() -> None:
    text = (
        "The road winds on.\n"
        "RECRUIT[Lyra]: elf ranger, level 3\n"
        "They camp for the night.\n"
        "recruit[Thrak] : half-orc barbarian, level 2\n"
    )
    tags = parse_recruit_tags(text)
    assert [(t.name, t.desc) for t in tags] == [
        ("Lyra", "elf ranger, level 3"),
        ("Thrak", "half-orc barbarian, level 2"),
    ]
    assert parse_recruit_tags("no tags here") == []
    assert parse_recruit_tags(None) == []


def test_prompt_vectors() -> None:
    sheets = [
        auto_sheet("Lyra", "elf", "ranger", 3, DATA),
        auto_sheet("Borin", "dwarf", "fighter", 1, DATA),
    ]
    assert dnd_party_prompt(sheets, DATA) == VECTORS["partyPrompt"]
    assert dnd_rules_text() == VECTORS["rulesText"]
    assert dnd_party_prompt([], DATA) == ""
