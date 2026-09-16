"""SRD data bundle loading (owned by DND-PORT).

The 18 JSON tables live vendored under ``content/dnd/`` with their
provenance README (official SRD 5.1, OGL 1.0a / CC-BY-4.0). Tables are
plain slug-keyed mappings; entries stay untyped JSON because only the
fields each rule touches are read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

DATA_FILES = [
    "spells",
    "monsters",
    "classes",
    "features",
    "subclasses",
    "skills",
    "weapons",
    "armor",
    "equipment",
    "magic-items",
    "races",
    "traits",
    "feats",
    "backgrounds",
    "conditions",
    "damage-types",
    "proficiencies",
    "xp",
]

REQUIRED_TABLES = ["spells", "monsters", "classes", "weapons", "armor", "races", "xp"]

DataTables = dict[str, dict[str, Any]]


def build_data(payload: dict[str, Any]) -> DataTables:
    """Validate a raw table mapping; raises on a missing core table."""
    for name in REQUIRED_TABLES:
        table = payload.get(name)
        if not isinstance(table, dict):
            raise ValueError(f"dnd data missing: {name}")
    return {name: payload[name] for name in DATA_FILES if isinstance(payload.get(name), dict)}


def load_data(base_dir: str | Path) -> DataTables:
    """Load every table from ``<base_dir>/<name>.json``."""
    root = Path(base_dir)
    payload: dict[str, Any] = {}
    for name in DATA_FILES:
        payload[name] = json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
    return build_data(payload)


def table(data: DataTables, name: str) -> dict[str, Any]:
    """One named table, or empty when absent or malformed."""
    found = data.get(name)
    return found if isinstance(found, dict) else {}


def entry(table_data: dict[str, Any], key: str) -> dict[str, Any]:
    """One table row by slug, or empty on miss."""
    found = table_data.get(key)
    return cast("dict[str, Any]", found) if isinstance(found, dict) else {}


def dict_field(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    """Nested mapping field, or empty when absent or malformed."""
    found = mapping.get(key)
    return cast("dict[str, Any]", found) if isinstance(found, dict) else {}


def list_field(mapping: dict[str, Any], key: str) -> list[Any]:
    """List field, or empty when absent or malformed."""
    found = mapping.get(key)
    return cast("list[Any]", found) if isinstance(found, list) else []


def int_field(mapping: dict[str, Any], key: str, default: int = 0) -> int:
    """Integer field; bools and non-numbers fall back to the default."""
    found = mapping.get(key)
    if isinstance(found, bool):
        return default
    return int(found) if isinstance(found, (int, float)) else default


def str_field(mapping: dict[str, Any], key: str) -> str | None:
    """String field, or ``None`` when absent or malformed."""
    found = mapping.get(key)
    return found if isinstance(found, str) else None
