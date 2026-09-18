"""Starter asset registration (owned by REVAMP-P04).

Curated files under content/assets/revamp/ are registered as ready
asset records, idempotently by content reference. Subjects resolve by
name against the target world; the regional map has no subject.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import UUID

from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.assets import AssetKind, AssetRecord
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_asset_id

STARTER_DIR = "revamp"
MANIFEST_FILE = "starter-manifest.json"


async def ensure_starter(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    assets_root: Path,
) -> list[AssetRecord]:
    """Register the curated starter set; repeat calls add nothing."""
    manifest_path = assets_root / STARTER_DIR / MANIFEST_FILE
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DomainError(ErrorCode.NOT_FOUND, "starter manifest is missing") from exc
    async with factory() as uow:
        await uow.worlds.get(world_id)
        characters = {c.name: c.id for c in await uow.characters.list_for_world(world_id)}
        locations = {loc.name: loc.id for loc in await uow.locations.list_for_world(world_id)}
        registered: list[AssetRecord] = []
        for entry in manifest["assets"]:
            ref = f"{STARTER_DIR}/{entry['file']}"
            existing = await uow.assets.find_asset_by_ref(world_id, ref)
            if existing is not None:
                registered.append(existing)
                continue
            subject = _resolve_subject(entry, characters, locations)
            asset = AssetRecord(
                id=new_asset_id(),
                world_id=world_id,
                kind=AssetKind(entry["kind"]),
                subject_id=subject,
                content_ref=ref,
                mime=entry["mime"],
                width=entry["width"],
                height=entry["height"],
                style_pack_version=manifest["style_pack_version"],
            )
            await uow.assets.add_asset(asset)
            registered.append(asset)
        await uow.commit()
        return registered


def _resolve_subject(
    entry: dict[str, object],
    characters: dict[str, UUID],
    locations: dict[str, UUID],
) -> UUID | None:
    subject = entry.get("subject")
    if subject is None:
        return None
    if not isinstance(subject, dict):
        raise DomainError(ErrorCode.VALIDATION_FAILED, "starter subject must be an object")
    fields = cast("dict[str, object]", subject)
    kind = fields.get("kind")
    name = fields.get("name")
    if not isinstance(kind, str) or not isinstance(name, str):
        return None
    if kind == "character":
        return characters.get(name)
    if kind == "location":
        return locations.get(name)
    return None
