"""D&D engine parity with perchance-ver/dnd.js (owned by DND-PORT).

Every vector in ``fixtures/dnd_vectors.json`` was generated from the
monolith by ``backend/scripts/gen_dnd_vectors.mjs``. Rolls replay the
scripted float sequences from the vector keys, so the comparison is
exact without matching Math.random. Known deviations (crit crash, heal
text, pure damage functions) are asserted separately below.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from worldsim.domain.rules.dnd import (
    HitPoints,
    Sheet,
    ability_mod,
    apply_damage,
    armor_ac,
    average_dice,
    build_sheet_summary,
    class_spell_list,
    create_monster_sheet,
    crit_damage_dice,
    describe_spell,
    encounter_difficulty,
    encounter_xp,
    ensure_hp,
    find_entry,
    fmt_mod,
    heal,
    known_spells,
    level_from_xp,
    level_up_preview,
    load_data,
    max_hp,
    monster_summary,
    parse_attack_tag,
    parse_cast_tag,
    parse_condition_tag,
    parse_dice,
    parse_encounter_tag,
    prof_bonus,
    race_ability_bonuses,
    resolve_spell,
    roll_attack,
    roll_dice,
    roll_save,
    sheet_mod,
    sheet_prof,
    slugify,
    spell_attack_bonus,
    spell_dc,
    spellcasting_ability,
    weapon_attack_bonus,
    xp_for_level,
    xp_for_next_level,
)
from worldsim.domain.rules.dnd.core import MonsterRef

ROOT = Path(__file__).parent.parent.parent
VECTORS: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "dnd_vectors.json").read_text(encoding="utf-8")
)["vectors"]
DATA = load_data(ROOT / "content" / "dnd")


def scripted(seq: list[float]) -> Callable[[], float]:
    state = {"i": 0}

    def draw() -> float:
        value = seq[state["i"] % len(seq)]
        state["i"] += 1
        return value

    return draw


def roll_notation(key: str) -> str:
    return key.split("@")[0]


def roll_seq(key: str) -> list[float]:
    return [float(v) for v in key.split("[")[1].rstrip("]").split(",")]


def test_parse_dice_vectors() -> None:
    for text, expected in VECTORS["parseDice"].items():
        parsed = parse_dice(text)
        if expected is None:
            assert parsed is None, text
        else:
            assert parsed is not None, text
            assert (parsed.count, parsed.sides, parsed.mod) == (
                expected["count"],
                expected["sides"],
                expected["mod"],
            ), text


def test_roll_and_average_vectors() -> None:
    for key, expected in VECTORS["rollDice"].items():
        seq = roll_seq(key) if "[" in key else [0.5]
        assert roll_dice(roll_notation(key), scripted(seq)) == expected, key
    assert average_dice("2d6+3") == VECTORS["averageDice"]["2d6+3"]
    assert average_dice("zzz") == 0


def test_ability_vectors() -> None:
    assert {int(k): ability_mod(int(k)) for k in VECTORS["abilityMod"]} == {
        int(k): v for k, v in VECTORS["abilityMod"].items()
    }
    for level, expected in VECTORS["profBonus"].items():
        assert prof_bonus(int(level)) == expected, level
    for value, expected in VECTORS["fmtMod"].items():
        assert fmt_mod(int(value)) == expected, value
    for text, expected in VECTORS["slugify"].items():
        assert slugify(text) == expected, text


def test_find_entry_vectors() -> None:
    for key, expected in VECTORS["findEntry"].items():
        table_name, _, query = key.partition(":")
        found = find_entry(DATA[table_name], query)
        if expected is None:
            assert found is None, key
        else:
            assert found is not None, key
            assert found.index == expected["index"], key
            assert found.entry["name"] == expected["name"], key


def test_xp_vectors() -> None:
    for level, expected in VECTORS["xpForLevel"].items():
        assert xp_for_level(int(level)) == expected, level
    for xp, expected in VECTORS["levelFromXp"].items():
        assert level_from_xp(int(xp)) == expected, xp
    assert xp_for_next_level(1, 0) == VECTORS["xpForNextLevel"]["L1"]
    assert xp_for_next_level(1, 100) == VECTORS["xpForNextLevel"]["L1partial"]
    assert xp_for_next_level(20, 400000) is None


def test_encounter_vectors() -> None:
    xp = encounter_xp(
        [MonsterRef(index="goblin", count=3), MonsterRef(index="bugbear", count=1)], DATA
    )
    expected = VECTORS["encounterXp"]
    assert (xp.total_xp, xp.adjusted_xp, xp.multiplier, xp.monster_count) == (
        expected["totalXp"],
        expected["adjustedXp"],
        expected["multiplier"],
        expected["monsterCount"],
    )
    diff = encounter_difficulty([3, 3], [MonsterRef(index="goblin", count=3)], DATA)
    want = VECTORS["encounterDifficulty"]
    assert diff.party_level == want["partyLevel"]
    assert diff.adjusted_xp == want["adjustedXp"]
    assert diff.thresholds == want["thresholds"]
    assert diff.difficulty == want["difficulty"]


def _fighter() -> Sheet:
    return Sheet(
        name="Borin",
        race="dwarf",
        character_class="fighter",
        level=3,
        stats={"str": 16, "dex": 12, "con": 15, "int": 8, "wis": 11, "cha": 10},
        armor="Chain Mail",
        shield=True,
        weapons=["longsword"],
        xp=900,
    )


def _wizard() -> Sheet:
    return Sheet(
        name="Elara",
        race="elf",
        character_class="wizard",
        level=5,
        stats={"str": 8, "dex": 14, "con": 13, "int": 17, "wis": 12, "cha": 10},
        weapons=["dagger"],
        spells=["fire-bolt", "fireball"],
        xp=6500,
    )


def test_sheet_vectors() -> None:
    defaults = Sheet()
    want = VECTORS["sheetDefaults"]
    assert defaults.name == want["name"]
    assert defaults.character_class == want["class"]
    assert defaults.stats == want["stats"]
    assert defaults.hp is None and defaults.weapons == [] and defaults.xp == 0

    fighter, wizard = _fighter(), _wizard()
    assert sheet_mod(fighter, "str") == VECTORS["sheetMod"]["str16"]
    assert sheet_mod(fighter, "int") == VECTORS["sheetMod"]["int8"]
    assert sheet_prof(fighter) == VECTORS["sheetProf"]["L3"]
    assert sheet_prof(wizard) == VECTORS["sheetProf"]["L5"]

    casting = VECTORS["spellcasting"]
    assert spellcasting_ability(DATA, fighter) == casting["fighter"]
    assert spellcasting_ability(DATA, wizard) == casting["wizard"]
    assert spell_dc(DATA, wizard) == casting["dc"]
    assert spell_attack_bonus(DATA, wizard) == casting["atk"]
    assert spell_dc(DATA, fighter) == casting["fighterDc"]

    attack = VECTORS["weaponAttack"]
    assert weapon_attack_bonus(DATA, fighter, DATA["weapons"]["longsword"]) == attack["longsword"]
    assert (
        weapon_attack_bonus(DATA, fighter, DATA["weapons"]["shortbow"]) == attack["shortbowRanged"]
    )
    assert weapon_attack_bonus(DATA, wizard, DATA["weapons"]["rapier"]) == attack["rapierFinesse"]

    ac = VECTORS["armorAC"]
    assert armor_ac(DATA, fighter) == ac["chainShield"]
    assert armor_ac(DATA, wizard) == ac["unarmored"]
    assert armor_ac(DATA, Sheet(armor="zzz-nope")) == ac["bogusArmor"]
    # Named-but-missing armor grants no Dex at all, even at DEX 18.
    dex_high = Sheet(
        stats={"str": 10, "dex": 18, "con": 10, "int": 10, "wis": 10, "cha": 10},
        armor="zzz-nope",
    )
    assert armor_ac(DATA, dex_high) == ac["missingArmorHighDex"] == 10

    hp = VECTORS["maxHp"]
    assert max_hp(DATA, fighter) == hp["fighter3"]
    assert max_hp(DATA, wizard) == hp["wizard5"]
    assert max_hp(DATA, Sheet(hp=HitPoints(current=5, max=44))) == hp["preset"]
    fresh = Sheet()
    assert ensure_hp(fresh, 18).model_dump() == VECTORS["ensureHp"]

    assert class_spell_list(DATA, wizard)[:5] == VECTORS["classSpells"]
    assert known_spells(wizard) == VECTORS["knownSpells"]
    assert race_ability_bonuses(DATA, "dwarf") == VECTORS["raceBonuses"]["dwarf"]
    assert race_ability_bonuses(DATA, "zzz") == {}

    assert build_sheet_summary(DATA, fighter) == VECTORS["sheetSummary"]["fighter"]
    assert build_sheet_summary(DATA, wizard) == VECTORS["sheetSummary"]["wizard"]


def _spell_sheet(key: str) -> Sheet:
    # Vectors use the full Elara sheet for fireball (INT 17 feeds the DC)
    # and plain levelled wizards for cantrips.
    if key.startswith("fireball"):
        return _wizard()
    level = 1 if key == "fireBolt1" else 11
    return Sheet(character_class="wizard", level=level)


SPELL_CASES = {
    "fireball3": ("fireball", 3),
    "fireball5": ("fireball", 5),
    "fireBolt1": ("fire-bolt", None),
    "fireBolt11": ("fire-bolt", None),
}


def test_spell_vectors() -> None:
    for key, (index, slot) in SPELL_CASES.items():
        want = VECTORS["resolveSpell"][key]
        resolved = resolve_spell(index, _spell_sheet(key), DATA, slot)
        assert resolved is not None, key
        got = resolved.model_dump()
        assert got["name"] == want["name"], key
        assert got["level"] == want["level"], key
        assert got["school"] == want["school"], key
        assert got["casting_time"] == want["castingTime"], key
        assert got["range"] == want["range"], key
        assert got["components"] == want["components"], key
        assert got["material"] == want["material"], key
        assert got["duration"] == want["duration"], key
        assert got["concentration"] == want["concentration"], key
        assert got["ritual"] == want["ritual"], key
        assert got["attack_type"] == want["attackType"], key
        assert got["classes"] == want["classes"], key
        if want["damage"] is None:
            assert got["damage"] is None, key
        else:
            assert got["damage"]["dice"] == want["damage"]["dice"], key
            assert got["damage"]["kind"] == want["damage"]["type"], key
            assert got["damage"]["slot_level"] == want["damage"]["slotLevel"], key
        if want["dc"] is None:
            assert got["dc"] is None, key
        else:
            assert got["dc"]["kind"] == want["dc"]["type"], key
            assert got["dc"]["success"] == want["dc"]["success"], key
            assert got["dc"]["dc_value"] == want["dc"]["dcValue"], key
    assert resolve_spell("zzz-nope", Sheet(), DATA) is None
    assert (
        describe_spell(resolve_spell("fireball", _wizard(), DATA, 3))
        == VECTORS["describeSpell"]["fireball3"]
    )
    assert (
        describe_spell(resolve_spell("fire-bolt", Sheet(character_class="wizard", level=1), DATA))
        == VECTORS["describeSpell"]["fireBolt1"]
    )
    assert describe_spell(None) is None


def test_heal_dice_deviation() -> None:
    """Monolith prints 'heals undefined'; the port resolves the slot dice."""
    assert VECTORS["describeSpell"]["cureWounds"] == "Cure Wounds, heals undefined, Touch"
    cleric = Sheet(
        name="Mira",
        character_class="cleric",
        level=3,
        stats={"str": 10, "dex": 10, "con": 12, "int": 10, "wis": 16, "cha": 10},
    )
    resolved = resolve_spell("cure-wounds", cleric, DATA, 1)
    assert resolved is not None and resolved.heal_dice == "1d8 + MOD"
    assert describe_spell(resolved) == "Cure Wounds, heals 1d8 + MOD, Touch"


def test_monster_vectors() -> None:
    sheet = create_monster_sheet("goblin", DATA)
    assert sheet is not None
    want = VECTORS["monsterSheet"]
    assert sheet.index == "goblin" and sheet.kind == "monster"
    assert sheet.hp.current == sheet.hp.max == want["hp"]["current"]
    assert sheet.name == want["name"]
    assert create_monster_sheet("zzz-nope", DATA) is None
    assert monster_summary("goblin", DATA) == VECTORS["monsterSummary"]["goblin"]
    assert monster_summary("aboleth", DATA) == VECTORS["monsterSummary"]["aboleth"]
    assert monster_summary("zzz", DATA) is None


def test_combat_roll_vectors() -> None:
    seqs = {"miss": [0.2], "hit": [0.5], "nat20": [0.9999], "nat1": [0.0]}
    bonuses = {"miss": (5, 18), "hit": (5, 12), "nat20": (0, 30), "nat1": (10, 5)}
    for key, expected in VECTORS["rollAttack"].items():
        bonus, ac = bonuses[key]
        got = roll_attack(bonus, ac, scripted(seqs[key]))
        assert (got.nat, got.total, got.nat20, got.nat1, got.hit, got.crit) == (
            expected["nat"],
            expected["total"],
            expected["nat20"],
            expected["nat1"],
            expected["hit"],
            expected["crit"],
        ), key
    save_seqs = {"fail": [0.2], "pass": [0.5], "nat20": [0.9999]}
    save_args = {"fail": (2, 15), "pass": (5, 12), "nat20": (0, 30)}
    for key, expected in VECTORS["rollSave"].items():
        bonus, dc = save_args[key]
        got = roll_save(bonus, dc, scripted(save_seqs[key]))
        assert (got.nat, got.total, got.nat20, got.nat1, got.success) == (
            expected["nat"],
            expected["total"],
            expected["nat20"],
            expected["nat1"],
            expected["success"],
        ), key


def test_damage_heal_vectors() -> None:
    want = VECTORS["applyDamage"]
    assert apply_damage(20, 20, 7.6) == (12, want["dealt"])
    assert apply_damage(12, 20, 99) == (0, want["overkill"])
    assert apply_damage(20, 20, 0) == (20, 0)
    got = VECTORS["heal"]
    assert heal(5, 20, 8.4) == (13, got["got"])
    assert heal(13, 20, 99) == (20, got["capped"])


def test_crit_deviation() -> None:
    """Crits double dice; the monolith crashes here (critDice undefined)."""
    assert crit_damage_dice("1d8") == "2d8"
    assert crit_damage_dice("2d6+3") == "4d6+3"
    assert crit_damage_dice("zzz") == "zzz"
    assert roll_dice("2d8", scripted([0.0, 0.0])) == 2


def test_level_up_vectors() -> None:
    preview = level_up_preview(Sheet(character_class="fighter", level=1), DATA)
    assert preview is not None
    want = VECTORS["levelUp"]["fighter2"]
    assert preview.new_level == want["newLevel"]
    assert preview.hp_gain == want["hpGain"]
    assert preview.prof_bonus == want["profBonus"]
    assert preview.prof_changed == want["profChanged"]
    assert preview.ability_score_bonus == want["abilityScoreBonus"]
    assert preview.features == want["features"]
    assert preview.cantrips_known == want["cantripsKnown"]
    assert preview.spells_known == want["spellsKnown"]
    assert preview.slots == want["slots"]
    assert preview.class_specific == want["classSpecific"]
    wizard = level_up_preview(Sheet(character_class="wizard", level=3), DATA)
    assert wizard is not None
    want_w = VECTORS["levelUp"]["wizard4"]
    assert wizard.slots == want_w["slots"]
    assert wizard.cantrips_known == want_w["cantripsKnown"]
    assert wizard.spells_known == want_w["spellsKnown"]
    assert level_up_preview(Sheet(character_class="fighter", level=20), DATA) is None


def test_tag_vectors() -> None:
    encounter_inputs = {
        "mixed": "2x Goblin, 1x Bugbear",
        "suffix": "goblin x3; orc",
        "words": "3 goblins and 1 ogre",
        "bogus": "zzz-nope",
        "empty": "",
    }
    for key, expected in VECTORS["parseEncounter"].items():
        got = [ref.model_dump() for ref in parse_encounter_tag(encounter_inputs[key], DATA)]
        assert got == expected, key
    cast_inputs = {
        "slotTarget": "fireball at 3rd level on goblins",
        "plain": "cure wounds",
        "bogus": "zzz-nope",
        "empty": "  ",
    }
    for key, expected in VECTORS["parseCast"].items():
        got = parse_cast_tag(cast_inputs[key], DATA)
        if expected is None:
            assert got is None, key
        else:
            assert got is not None, key
            assert (got.index, got.name, got.slot_level, got.target) == (
                expected["index"],
                expected["name"],
                expected["slotLevel"],
                expected["target"],
            ), key
    attack_inputs = {"target": "longsword at goblin", "plain": "dagger", "bogus": "zzz-nope"}
    for key, expected in VECTORS["parseAttack"].items():
        got = parse_attack_tag(attack_inputs[key], DATA)
        assert got is not None, key
        assert (got.index, got.name, got.target) == (
            expected["index"],
            expected["name"],
            expected["target"],
        ), key
    condition_inputs = {
        "full": "poisoned on goblin for 3 rounds",
        "plain": "prone",
        "bogus": "zzz-nope",
    }
    for key, expected in VECTORS["parseCondition"].items():
        got = parse_condition_tag(condition_inputs[key], DATA)
        assert got is not None, key
        assert (got.index, got.name, got.target, got.duration) == (
            expected["index"],
            expected["name"],
            expected["target"],
            expected["duration"],
        ), key


def test_data_bundle_guards() -> None:
    from worldsim.domain.rules.dnd.data import build_data

    assert set(DATA) >= {"spells", "monsters", "classes", "xp"}
    try:
        build_data({"spells": {}})
    except ValueError as exc:
        assert "dnd data missing" in str(exc)
    else:
        raise AssertionError("build_data accepted an incomplete bundle")


def test_seeded_rng_reproducible() -> None:
    import random

    first = roll_dice("8d6", random.Random(42).random)
    second = roll_dice("8d6", random.Random(42).random)
    assert first == second
