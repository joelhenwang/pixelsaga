"""Built-in Library presets with stable identities (owned by MAINMENU-A03).

The 0030 migration inserts the same rows for fresh upgrades; this service
keeps older databases converging and is safe to call repeatedly: existing
IDs are never rewritten.
"""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.presets import (
    CharacterPresetPayload,
    Preset,
    PresetKind,
    PresetPayload,
    PresetRevision,
    StylePackPayload,
    TemplatePresetPayload,
    WorldLocationPreset,
    WorldPresetPayload,
)
from worldsim.domain.time import utcnow

WORLD_PRESET_ID = UUID("20000000-0000-4000-8000-000000000001")
WREN_PRESET_ID = UUID("20000000-0000-4000-8000-000000000101")
ASH_PRESET_ID = UUID("20000000-0000-4000-8000-000000000102")
STYLE_PRESET_ID = UUID("20000000-0000-4000-8000-000000000201")
TEMPLATE_PRESET_ID = UUID("20000000-0000-4000-8000-000000000301")


def _hash(payload: PresetPayload) -> str:
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def builtin_definitions() -> list[tuple[UUID, PresetKind, str, PresetPayload]]:
    world = WorldPresetPayload(
        name="Ember Vale",
        description="A sheltered vale of hearths, markets, and old roads.",
        lore="The vale keeps its stories close.",
        locations=[
            WorldLocationPreset(key="hearth", name="Hearth"),
            WorldLocationPreset(key="market", name="Market"),
        ],
        travel=[],
        starting_location_key="hearth",
        default_cast=["wren", "ash"],
        style_pack_id="anime-saga-v1",
    )
    wren = CharacterPresetPayload(
        name="Wren",
        appearance="Quick eyes and a traveler's coat.",
        personality="Curious, kind, asks what if.",
        background="Road-raised and story-fed.",
        portrait_asset_id=None,
        tags=["Human", "Explorer", "Player-ready"],
        starting_location_key="hearth",
    )
    ash = CharacterPresetPayload(
        name="Ash",
        appearance="Steady stance, weather-worn cloak.",
        personality="Patient, dry-witted, dependable.",
        background="Market ward born and bred.",
        portrait_asset_id=None,
        tags=["Human", "Wanderer", "Player-ready"],
        starting_location_key="market",
    )
    style = StylePackPayload(
        display_name="Anime Saga",
        style_id="anime-saga-v1",
        guidance="Warm anime-fantasy key art with expressive portraits.",
    )
    template = TemplatePresetPayload(
        display_name="Ember Vale opening",
        world_preset_id=str(WORLD_PRESET_ID),
        world_preset_revision=1,
        cast_preset_ids=[str(WREN_PRESET_ID), str(ASH_PRESET_ID)],
        tone="hopeful mystery",
        pacing="measured",
    )
    return [
        (WORLD_PRESET_ID, PresetKind.WORLD, "Ember Vale", world),
        (WREN_PRESET_ID, PresetKind.CHARACTER, "Wren", wren),
        (ASH_PRESET_ID, PresetKind.CHARACTER, "Ash", ash),
        (STYLE_PRESET_ID, PresetKind.STYLE_PACK, "Anime Saga", style),
        (TEMPLATE_PRESET_ID, PresetKind.TEMPLATE, "Ember Vale opening", template),
    ]


async def ensure_builtin_presets(uow: UnitOfWork) -> int:
    """Insert missing built-ins with their revision 1; return the count added."""
    added = 0
    now = utcnow()
    for preset_id, kind, name, payload in builtin_definitions():
        if await uow.presets.find_preset(preset_id) is not None:
            continue
        await uow.presets.add_preset(
            Preset(
                id=preset_id,
                kind=kind,
                name=name,
                builtin=True,
                readonly=True,
                created_at=now,
            )
        )
        await uow.presets.add_revision(
            PresetRevision(
                preset_id=preset_id,
                revision=1,
                schema_version=1,
                payload=payload,
                content_hash=_hash(payload),
                created_at=now,
            )
        )
        added += 1
    return added
