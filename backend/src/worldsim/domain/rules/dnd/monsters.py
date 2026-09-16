"""Monster sheets and summaries (owned by DND-PORT).

Port of createMonsterSheet/monsterSummary. A monster sheet keeps the
full raw entry (extra fields allowed) with live hit points attached.
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from worldsim.domain.rules.dnd.core import ABILITY_KEYS, ability_mod, fmt_mod
from worldsim.domain.rules.dnd.data import (
    DataTables,
    dict_field,
    entry,
    int_field,
    list_field,
    str_field,
    table,
)
from worldsim.domain.rules.dnd.sheets import HitPoints


class MonsterSheet(BaseModel):
    """Raw monster entry plus live HP. Unknown fields pass through."""

    model_config = ConfigDict(extra="allow")

    index: str
    kind: str = "monster"
    name: str = "Monster"
    hp: HitPoints


def create_monster_sheet(index: str, data: DataTables) -> MonsterSheet | None:
    """Attach a full HP track to a monster entry; ``None`` on miss."""
    monsters = data.get("monsters") or {}
    raw = monsters.get(index)
    if not isinstance(raw, dict):
        return None
    row = cast("dict[str, Any]", raw)
    maximum = int(row.get("hp", 0) or 0)
    extras = {k: v for k, v in row.items() if k not in ("hp", "index", "kind", "name")}
    return MonsterSheet(
        **extras,
        index=index,
        name=str(row.get("name", index)),
        hp=HitPoints(current=maximum, max=maximum),
    )


def monster_summary(index: str, data: DataTables) -> str | None:
    """Exact ``[MONSTER]`` text the monolith feeds the narrator."""
    row = entry(table(data, "monsters"), index)
    if not row:
        return None
    hit_dice = str_field(row, "hit_dice")
    lines = [
        f"[MONSTER] {str_field(row, 'name')} ({str_field(row, 'size') or ''} "
        f"{str_field(row, 'type') or ''}, CR {row.get('cr')}, {row.get('xp')} XP): "
        f"AC {row.get('ac')}, HP {row.get('hp')}" + (f" ({hit_dice})" if hit_dice else "")
    ]
    speed = dict_field(row, "speed")
    rendered = ", ".join(
        str(value).rstrip(".") if key == "walk" else f"{key} {str(value).rstrip('.')}"
        for key, value in speed.items()
    )
    if rendered:
        lines.append(f"Speed: {rendered}")
    stats = dict_field(row, "stats")
    lines.append(
        " ".join(
            f"{key.upper()} {fmt_mod(ability_mod(int_field(stats, key, 10)))}"
            for key in ABILITY_KEYS
        )
    )
    saves = dict_field(row, "saves")
    if saves:
        lines.append("Saves: " + ", ".join(f"{k} {fmt_mod(int_field(saves, k))}" for k in saves))
    skills = dict_field(row, "skills")
    if skills:
        lines.append(
            "Skills: "
            + ", ".join(f"{k.replace('_', ' ')} {fmt_mod(int_field(skills, k))}" for k in skills)
        )
    for label, key in (
        ("Resist", "resistances"),
        ("Immune", "immunities"),
        ("Vuln", "vulnerabilities"),
    ):
        values = [str(v) for v in list_field(row, key)]
        if values:
            lines.append(f"{label}: " + ", ".join(values))
    cond_imm = [str(v) for v in list_field(row, "condition_immunities")]
    if cond_imm:
        lines.append("Cond imm: " + ", ".join(cond_imm))
    rendered_actions: list[str] = []
    for action in list_field(row, "actions")[:5]:
        if not isinstance(action, dict):
            continue
        item = cast("dict[str, Any]", action)
        text = str_field(item, "name") or ""
        attack_bonus = item.get("attack_bonus")
        if attack_bonus is not None:
            text += f" +{attack_bonus}"
        dc = dict_field(item, "dc")
        if dc:
            text += f" (DC {dc.get('dc')} {str_field(dc, 'type')})"
        dealt = [
            f"{str_field(cast('dict[str, Any]', part), 'dice')} "
            f"{str_field(cast('dict[str, Any]', part), 'type')}"
            for part in list_field(item, "damage")
            if isinstance(part, dict)
        ]
        if dealt:
            text += " (" + " + ".join(dealt) + ")"
        rendered_actions.append(text)
    if rendered_actions:
        lines.append("Actions: " + ", ".join(rendered_actions))
    return ". ".join(lines)
