"""Item definition content loading (owned by S2-PROGRESS-001).

Definitions are content, not canon: the JSON file owns names,
weights, and stackability; the database owns instances and their
single holder. Unknown keys fail loudly at give time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ItemDefinition(BaseModel):
    """One catalogued item kind."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=1024)
    weight: int = Field(default=0, ge=0)
    stackable: bool = False


def load_item_definitions(path: str | Path) -> dict[str, ItemDefinition]:
    """Load and validate the item catalog; duplicate keys fail."""
    raw: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = raw["items"]
    catalog: dict[str, ItemDefinition] = {}
    for entry in entries:
        definition = ItemDefinition.model_validate(entry)
        if definition.key in catalog:
            raise ValueError(f"duplicate item key: {definition.key}")
        catalog[definition.key] = definition
    return catalog
