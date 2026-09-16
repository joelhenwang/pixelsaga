"""LLM tag parsers (owned by DND-PORT).

Port of parseEncounterTag/parseCastTag/parseAttackTag/parseConditionTag:
structured resolution of the ``ENCOUNTER[...]``/``CAST[...]`` style tags
the narrator emits. Unrecognized names resolve to ``index=None`` with the
raw text kept; empty input returns ``None`` (encounter tags return ``[]``).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from worldsim.domain.rules.dnd.core import find_entry
from worldsim.domain.rules.dnd.data import DataTables

_ENCOUNTER_SPLIT_RE = re.compile(r"[,;]|\band\b", re.IGNORECASE)
_COUNT_PREFIX_RE = re.compile(r"^(\d+)\s*x\s*(.+)$", re.IGNORECASE)
_COUNT_SUFFIX_RE = re.compile(r"^(.+?)\s*x\s*(\d+)$", re.IGNORECASE)
_COUNT_BARE_RE = re.compile(r"^(\d+)\s+(.+)$", re.IGNORECASE)
_SLOT_RE = re.compile(r"at\s+(\d+)(?:st|nd|rd|th)?\s+level", re.IGNORECASE)
_TARGET_RE = re.compile(r"\b(?:on|at|against|vs\.?)\s+(.+)$", re.IGNORECASE)
_ATTACK_TARGET_RE = re.compile(r"\b(?:at|on|against|vs\.?)\s+(.+)$", re.IGNORECASE)
_DURATION_RE = re.compile(r"for\s+(\d+)\s+(round|turn|minute|second)s?", re.IGNORECASE)
_CONDITION_TARGET_RE = re.compile(r"\b(?:on|at|against)\s+(.+)$", re.IGNORECASE)


class EncounterRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: str
    name: str
    count: int = 1


class CastTag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: str | None
    name: str
    slot_level: int | None = None
    target: str | None = None


class AttackTag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: str | None
    name: str
    target: str | None = None


class ConditionTag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: str | None
    name: str
    target: str | None = None
    duration: str | None = None


def _lookup(table: dict[str, Any] | None, text: str) -> tuple[str | None, str]:
    found = find_entry(table, text)
    if found:
        return found.index, str(found.entry.get("name", text))
    return None, text


def parse_encounter_tag(raw: str | None, data: DataTables) -> list[EncounterRef]:
    """Split ``2x Goblin, 1x Bugbear`` into monster references."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    table = data.get("monsters")
    out: list[EncounterRef] = []
    for chunk in _ENCOUNTER_SPLIT_RE.split(raw):
        chunk = chunk.strip()
        if not chunk:
            continue
        count = 1
        match = _COUNT_PREFIX_RE.match(chunk)
        if match:
            count, chunk = int(match.group(1)), match.group(2).strip()
        else:
            match = _COUNT_SUFFIX_RE.match(chunk)
            if match:
                chunk, count = match.group(1).strip(), int(match.group(2))
            else:
                match = _COUNT_BARE_RE.match(chunk)
                if match:
                    count, chunk = int(match.group(1)), match.group(2).strip()
        index, name = _lookup(table, chunk)
        if index is not None:
            out.append(EncounterRef(index=index, name=name, count=count))
    return out


def parse_cast_tag(raw: str | None, data: DataTables) -> CastTag | None:
    """Parse ``fireball at 3rd level on goblins`` into spell + slot + target."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    slot_level: int | None = None
    match = _SLOT_RE.search(text)
    if match:
        slot_level = int(match.group(1))
        text = (text[: match.start()] + " " + text[match.end() :]).strip()
    target: str | None = None
    match = _TARGET_RE.search(text)
    if match:
        target = match.group(1).strip()
        text = (text[: match.start()] + " " + text[match.end() :]).strip()
    if not text:
        return None
    index, name = _lookup(data.get("spells"), text)
    return CastTag(index=index, name=name, slot_level=slot_level, target=target)


def parse_attack_tag(raw: str | None, data: DataTables) -> AttackTag | None:
    """Parse ``longsword at goblin`` into weapon + target."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    target: str | None = None
    match = _ATTACK_TARGET_RE.search(text)
    if match:
        target = match.group(1).strip()
        text = (text[: match.start()] + " " + text[match.end() :]).strip()
    if not text:
        return None
    index, name = _lookup(data.get("weapons"), text)
    return AttackTag(index=index, name=name, target=target)


def parse_condition_tag(raw: str | None, data: DataTables) -> ConditionTag | None:
    """Parse ``poisoned on goblin for 3 rounds`` into condition + target + duration."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    duration: str | None = None
    match = _DURATION_RE.search(text)
    if match:
        duration = f"{int(match.group(1))} {match.group(2)}"
        text = (text[: match.start()] + " " + text[match.end() :]).strip()
    target: str | None = None
    match = _CONDITION_TARGET_RE.search(text)
    if match:
        target = match.group(1).strip()
        text = (text[: match.start()] + " " + text[match.end() :]).strip()
    if not text:
        return None
    index, name = _lookup(data.get("conditions"), text)
    return ConditionTag(index=index, name=name, target=target, duration=duration)


_RECRUIT_RE = re.compile(r"RECRUIT\s*\[([^\]]+)\]\s*:\s*(.+?)(?:\n|$)", re.IGNORECASE)


class RecruitTag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    desc: str


def parse_recruit_tags(text: str | None) -> list[RecruitTag]:
    """Scan narration for ``RECRUIT[Name]: race class, level N`` tags.

    Mirrors the monolith's streaming-tolerant scan: every match counts,
    and name de-duplication stays with the caller (party membership).
    """
    if not isinstance(text, str) or not text.strip():
        return []
    return [
        RecruitTag(name=match.group(1).strip(), desc=match.group(2).strip())
        for match in _RECRUIT_RE.finditer(text)
        if match.group(1).strip()
    ]
