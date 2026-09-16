"""Deterministic combat tag resolution (owned by DND-WIRE-2).

Deep module: narration text goes in, a full combat report comes out.
No I/O, and the input sheets are never mutated (rolls run against
copies); the caller persists HP deltas and beats. Tags resolve in
source order against one RNG stream, so a seeded stream replays
exactly.

Attackers match by loadout: the first roster sheet carrying the tagged
weapon or spell rolls. Party targets resolve by name; anything else
falls back to the monster tables with ephemeral HP (the monolith never
persisted monster state either). Saves use class saving throws for
adventurers and the precomputed bonuses for monsters.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from worldsim.domain.rules.dnd.combat import (
    roll_attack,
    roll_damage,
    roll_dice,
    roll_save,
)
from worldsim.domain.rules.dnd.core import (
    MonsterRef,
    ability_mod,
    encounter_difficulty,
    find_entry,
    slugify,
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
from worldsim.domain.rules.dnd.sheets import (
    Sheet,
    armor_ac,
    sheet_mod,
    sheet_prof,
    spell_attack_bonus,
    spellcasting_ability,
    weapon_attack_bonus,
)
from worldsim.domain.rules.dnd.spells import resolve_spell
from worldsim.domain.rules.dnd.tags import (
    parse_attack_tag,
    parse_cast_tag,
    parse_condition_tag,
    parse_encounter_tag,
)

_TAG_RE = re.compile(
    r"^\s*(ENCOUNTER|ATTACK|CAST|CONDITION)\s*\[([^\]]+)\]",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class CombatBeat:
    text: str
    cited: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TagOutcome:
    kind: str
    text: str
    attacker_key: str | None = None
    target_key: str | None = None


@dataclass(frozen=True)
class MonsterState:
    """Live pool carried in: one row per world and name key."""

    key: str
    name: str
    hp_current: int
    hp_max: int
    ac: int


@dataclass(frozen=True)
class MonsterResult:
    """Pool to persist: working HP plus the max/AC that own it."""

    key: str
    name: str
    hp_current: int
    hp_max: int
    ac: int
    spawned: bool


@dataclass(frozen=True)
class CombatReport:
    outcomes: list[TagOutcome] = field(default_factory=list)
    hp: dict[str, int] = field(default_factory=dict)
    conditions: dict[str, list[str]] = field(default_factory=dict)
    monsters: dict[str, MonsterResult] = field(default_factory=dict)
    beats: list[CombatBeat] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


@dataclass
class _MonsterTarget:
    label: str
    ac: int
    hp: int
    key: str


def _sheet_key(name: str) -> str:
    return f"dnd-sheet:{slugify(name)}"


def _party_position(order: list[Sheet], keys: list[str], target: str | None) -> int | None:
    if not target:
        return None
    want = target.strip().lower()
    for pos, sheet in enumerate(order):
        if sheet.name.lower() == want or keys[pos] == want:
            return pos
    return None


def _monster_target(
    tables: DataTables, monsters: dict[str, Any], name: str | None
) -> _MonsterTarget:
    found = find_entry(monsters, name or "")
    if found is None:
        return _MonsterTarget(label=name or "the air", ac=10, hp=0, key=(name or "unknown").lower())
    row = found.entry
    return _MonsterTarget(
        label=str(row.get("name", name)),
        ac=int_field(row, "ac", 10),
        hp=int_field(row, "hp"),
        key=found.index,
    )


def _save_bonus(
    tables: DataTables, sheet: Sheet, ability: str, monster: dict[str, Any] | None
) -> int:
    if monster is not None:
        saves = dict_field(monster, "saves")
        direct = saves.get(ability)
        if isinstance(direct, int) and not isinstance(direct, bool):
            return direct
        return ability_mod(int_field(dict_field(monster, "stats"), ability, 10))
    mod = sheet_mod(sheet, ability)
    cls = entry(table(tables, "classes"), sheet.character_class)
    throws = [str(t).lower() for t in list_field(cls, "saving_throws")]
    if ability in throws:
        mod += sheet_prof(sheet)
    return mod


def resolve_narration_tags(
    text: str,
    sheets: list[Sheet],
    tables: DataTables,
    rng: Callable[[], float] | None = None,
    live: list[MonsterState] | None = None,
) -> CombatReport:
    """Resolve every combat tag in narration order. Inputs are never mutated.

    ``monsters`` carries live pools from earlier scenes; unknown keys
    start at the table maximum and a fresh ENCOUNTER respawns its keys
    to full.
    """
    if not text or not sheets:
        return CombatReport()
    order = list(sheets)
    currents = {id(sheet): (sheet.hp.current if sheet.hp else 0) for sheet in order}
    maxima = {id(sheet): (sheet.hp.max if sheet.hp else 0) for sheet in order}
    keys = [slugify(sheet.name) for sheet in order]
    key_of = {id(sheet): key for sheet, key in zip(order, keys, strict=True)}
    monsters = table(tables, "monsters")
    weapons = table(tables, "weapons")
    carried = {state.key: state for state in live or []}
    monster_hp = {
        key: max(0, min(state.hp_current, state.hp_max)) for key, state in carried.items()
    }
    monster_meta: dict[str, _MonsterTarget] = {}
    for key, state in carried.items():
        monster_meta[key] = _MonsterTarget(label=state.name, ac=state.ac, hp=state.hp_max, key=key)
    outcomes: list[TagOutcome] = []
    beats: list[CombatBeat] = []
    unresolved: list[str] = []
    hp_updates: dict[str, int] = {}
    new_conditions: dict[str, list[str]] = {}

    def cite(*members: str | None) -> list[str]:
        return [_sheet_key(key) for key in members if key]

    def hurt_party(pos: int, amount: int) -> tuple[int, int]:
        sheet = order[pos]
        before = currents[id(sheet)]
        after = max(0, before - amount)
        currents[id(sheet)] = after
        hp_updates[key_of[id(sheet)]] = after
        return before, after

    def mend_party(pos: int, amount: int) -> tuple[int, int]:
        sheet = order[pos]
        before = currents[id(sheet)]
        after = min(maxima[id(sheet)], before + amount)
        currents[id(sheet)] = after
        hp_updates[key_of[id(sheet)]] = after
        return before, after

    damaged: set[str] = set()
    spawned: set[str] = set()

    def hurt_monster(target: _MonsterTarget, amount: int) -> tuple[int, int]:
        monster_meta.setdefault(target.key, target)
        start = monster_hp.get(target.key, target.hp)
        after = max(0, start - amount)
        monster_hp[target.key] = after
        if after != start:
            damaged.add(target.key)
        return start, after

    for match in _TAG_RE.finditer(text):
        kind, inner = match.group(1).upper(), match.group(2).strip()
        if kind == "ENCOUNTER":
            refs = parse_encounter_tag(inner, tables)
            if not refs:
                unresolved.append(match.group(0))
                continue
            diff = encounter_difficulty(
                [s.level for s in order],
                [MonsterRef(index=r.index, count=r.count) for r in refs],
                tables,
            )
            for ref in refs:
                encounter_row = entry(monsters, ref.index)
                fresh = _MonsterTarget(
                    label=str(encounter_row.get("name", ref.name)),
                    ac=int_field(encounter_row, "ac", 10),
                    hp=int_field(encounter_row, "hp"),
                    key=ref.index,
                )
                monster_hp[ref.index] = fresh.hp
                monster_meta[ref.index] = fresh
                spawned.add(ref.index)
            described = ", ".join(f"{r.count}x {r.name}" if r.count > 1 else r.name for r in refs)
            outcomes.append(
                TagOutcome(
                    kind="encounter",
                    text=f"Encounter: {described} ({diff.difficulty}, "
                    f"{diff.adjusted_xp} adjusted XP).",
                )
            )
            beats.append(
                CombatBeat(
                    text=f"{described} bar the way ({diff.difficulty} encounter).",
                    cited=[_sheet_key(key) for key in keys],
                )
            )
            continue
        if kind == "ATTACK":
            tag = parse_attack_tag(inner, tables)
            attacker = None
            if tag is not None:
                attacker = next((s for s in order if tag.index and tag.index in s.weapons), None)
                if attacker is None and tag.index is None:
                    attacker = next((s for s in order if tag.name in s.weapons), None)
            if tag is None or attacker is None:
                unresolved.append(match.group(0))
                continue
            akey = key_of[id(attacker)]
            weapon = entry(weapons, tag.index) if tag.index else {}
            bonus = weapon_attack_bonus(tables, attacker, weapon)
            pos = _party_position(order, keys, tag.target)
            if pos is not None:
                target_ac = armor_ac(tables, order[pos])
                target: str | _MonsterTarget = order[pos].name
                tkey: str | None = keys[pos]
            else:
                target = _monster_target(tables, monsters, tag.target)
                target_ac = target.ac
                tkey = None
            label = target if isinstance(target, str) else target.label
            attack = roll_attack(bonus, target_ac, rng)
            if not attack.hit:
                outcomes.append(
                    TagOutcome(
                        kind="attack",
                        attacker_key=akey,
                        text=f"{attacker.name} misses {label} ({attack.total} vs AC {target_ac}).",
                    )
                )
                beats.append(
                    CombatBeat(
                        text=f"{attacker.name}'s {tag.name} misses {label}.",
                        cited=cite(akey, tkey),
                    )
                )
                continue
            damage = dict_field(weapon, "damage")
            dice = str_field(damage, "dice")
            dtype = str_field(damage, "type") or "damage"
            rolled = roll_damage(dice, rng, attack.crit)
            if pos is not None:
                before, after = hurt_party(pos, rolled)
            else:
                assert isinstance(target, _MonsterTarget)
                before, after = hurt_monster(target, rolled)
            crit = " Critical!" if attack.crit else ""
            outcomes.append(
                TagOutcome(
                    kind="attack",
                    attacker_key=akey,
                    target_key=tkey,
                    text=f"{attacker.name} hits {label} for {rolled} {dtype}.{crit} "
                    f"({before}->{after} HP)",
                )
            )
            beats.append(
                CombatBeat(
                    text=f"{attacker.name}'s {tag.name} hits {label} for {rolled} {dtype}.{crit}",
                    cited=cite(akey, tkey),
                )
            )
            continue
        if kind == "CAST":
            tag = parse_cast_tag(inner, tables)
            attacker = None
            if tag is not None and tag.index:
                attacker = next((s for s in order if tag.index in s.spells), None)
            if tag is None or attacker is None:
                unresolved.append(match.group(0))
                continue
            akey = key_of[id(attacker)]
            resolved = resolve_spell(tag.index or "", attacker, tables, tag.slot_level)
            if resolved is None:
                unresolved.append(match.group(0))
                continue
            pos = _party_position(order, keys, tag.target)
            if resolved.damage is None and resolved.heal_dice is None:
                outcomes.append(
                    TagOutcome(
                        kind="cast",
                        attacker_key=akey,
                        text=f"{attacker.name} casts {resolved.name} "
                        f"({tag.target or 'no target'}).",
                    )
                )
                beats.append(
                    CombatBeat(text=f"{attacker.name} casts {resolved.name}.", cited=cite(akey))
                )
                continue
            if resolved.damage is None:
                assert resolved.heal_dice is not None
                ability = spellcasting_ability(tables, attacker) or "wis"
                dice = resolved.heal_dice.replace("MOD", str(sheet_mod(attacker, ability)))
                rolled = roll_dice(dice, rng)
                if pos is not None:
                    before, after = mend_party(pos, rolled)
                    label, tkey = order[pos].name, keys[pos]
                    trail = f" ({before}->{after} HP)"
                else:
                    label, tkey, trail = tag.target or "the air", None, " (no one to mend)"
                outcomes.append(
                    TagOutcome(
                        kind="cast",
                        attacker_key=akey,
                        target_key=tkey,
                        text=f"{attacker.name} heals {label} for {rolled}.{trail}",
                    )
                )
                beats.append(
                    CombatBeat(
                        text=f"{attacker.name}'s {resolved.name} mends {label} for {rolled}.",
                        cited=cite(akey, tkey),
                    )
                )
                continue
            assert resolved.damage is not None
            dtype = resolved.damage.kind or "damage"
            if resolved.attack_type is not None:
                bonus = spell_attack_bonus(tables, attacker) or 0
                if pos is not None:
                    target_ac = armor_ac(tables, order[pos])
                    label, tkey = order[pos].name, keys[pos]
                else:
                    monster = _monster_target(tables, monsters, tag.target)
                    target_ac, label, tkey = monster.ac, monster.label, None
                attack = roll_attack(bonus, target_ac, rng)
                if not attack.hit:
                    outcomes.append(
                        TagOutcome(
                            kind="cast",
                            attacker_key=akey,
                            text=f"{resolved.name} misses {label} "
                            f"({attack.total} vs AC {target_ac}).",
                        )
                    )
                    beats.append(
                        CombatBeat(
                            text=f"{attacker.name}'s {resolved.name} misses {label}.",
                            cited=cite(akey, tkey),
                        )
                    )
                    continue
                rolled = roll_damage(resolved.damage.dice, rng, attack.crit)
                crit = " Critical!" if attack.crit else ""
                detail = f"hits {label} for {rolled} {dtype}.{crit}"
            else:
                dc = resolved.dc
                save_ability = (dc.kind if dc else None) or "dex"
                dc_value = dc.dc_value if dc and dc.dc_value is not None else 10
                success_word = (dc.success if dc and dc.success else None) or "none"
                if pos is not None:
                    bonus = _save_bonus(tables, order[pos], save_ability, None)
                    label, tkey = order[pos].name, keys[pos]
                else:
                    monster = _monster_target(tables, monsters, tag.target)
                    row = entry(monsters, monster.key) if monster.key in monsters else {}
                    bonus = _save_bonus(tables, attacker, save_ability, row or None)
                    label, tkey = monster.label, None
                save = roll_save(bonus, dc_value, rng)
                if save.success and success_word == "half":
                    rolled = math.floor(roll_dice(resolved.damage.dice, rng) / 2)
                    how = f"saves ({save.total} vs DC {dc_value}), half damage"
                elif save.success:
                    rolled, how = 0, f"saves ({save.total} vs DC {dc_value}), unharmed"
                else:
                    rolled = roll_dice(resolved.damage.dice, rng)
                    how = f"fails ({save.total} vs DC {dc_value})"
                detail = f"{label} {how} for {rolled} {dtype}."
            if pos is not None:
                before, after = hurt_party(pos, rolled)
                trail = f" ({before}->{after} HP)"
            else:
                monster = _monster_target(tables, monsters, tag.target)
                before, after = hurt_monster(monster, rolled)
                trail = f" ({before}->{after} HP)"
            outcomes.append(
                TagOutcome(
                    kind="cast",
                    attacker_key=akey,
                    target_key=tkey,
                    text=f"{resolved.name} {detail}{trail}",
                )
            )
            beats.append(
                CombatBeat(
                    text=f"{attacker.name}'s {resolved.name} {detail}",
                    cited=cite(akey, tkey),
                )
            )
            continue
        if kind == "CONDITION":
            tag = parse_condition_tag(inner, tables)
            if tag is None:
                unresolved.append(match.group(0))
                continue
            pos = _party_position(order, keys, tag.target)
            if tag.index:
                label = str(entry(table(tables, "conditions"), tag.index).get("name", tag.name))
            else:
                label = tag.name
            if pos is not None:
                seen = new_conditions.get(keys[pos], list(order[pos].conditions))
                if label not in seen:
                    seen = seen + [label]
                new_conditions[keys[pos]] = seen
                tkey, tlabel = keys[pos], order[pos].name
            else:
                tkey, tlabel = None, tag.target or "the air"
            span = f" ({tag.duration})" if tag.duration else ""
            outcomes.append(
                TagOutcome(kind="condition", target_key=tkey, text=f"{label} on {tlabel}{span}.")
            )
            beats.append(CombatBeat(text=f"{tlabel} is {label.lower()}{span}.", cited=cite(tkey)))
            continue
        unresolved.append(match.group(0))

    persisted = {
        key: MonsterResult(
            key=key,
            name=monster_meta[key].label,
            hp_current=monster_hp[key],
            hp_max=monster_meta[key].hp,
            ac=monster_meta[key].ac,
            spawned=key in spawned,
        )
        for key in sorted(set(spawned) | damaged)
        if key in monster_meta and key in monster_hp
    }
    return CombatReport(
        outcomes=outcomes,
        hp=hp_updates,
        conditions=new_conditions,
        monsters=persisted,
        beats=beats,
        unresolved=unresolved,
    )
