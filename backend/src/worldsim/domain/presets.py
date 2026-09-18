"""Reusable Library presets with immutable revisions.

A preset is a template; a revision is its validated typed payload frozen at a
content hash. Stories and drafts pin revisions, so editing a preset never
rewrites an existing story. Built-ins are read-only seeds duplicated before
editing.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.ids import PresetId
from worldsim.domain.time import utcnow


class PresetKind(StrEnum):
    WORLD = "world"
    CHARACTER = "character"
    STYLE_PACK = "style_pack"
    TEMPLATE = "template"


class WorldLocationPreset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class WorldPresetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["world"] = "world"
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    lore: str | None = Field(default=None, max_length=8000)
    locations: list[WorldLocationPreset] = Field(min_length=1, max_length=64)
    travel: list[list[str]] = Field(default_factory=list)
    starting_location_key: str = Field(min_length=1, max_length=64)
    default_cast: list[str] = Field(default_factory=list)
    style_pack_id: str | None = Field(default=None, max_length=128)


class CharacterPresetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["character"] = "character"
    name: str = Field(min_length=1, max_length=64)
    appearance: str | None = Field(default=None, max_length=2000)
    personality: str | None = Field(default=None, max_length=2000)
    background: str | None = Field(default=None, max_length=4000)
    portrait_asset_id: str | None = Field(default=None, max_length=128)
    tags: list[str] = Field(default_factory=list, max_length=16)
    starting_location_key: str | None = Field(default=None, max_length=64)


class StylePackPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["style_pack"] = "style_pack"
    display_name: str = Field(min_length=1, max_length=128)
    style_id: str = Field(min_length=1, max_length=64)
    guidance: str | None = Field(default=None, max_length=8000)


class TemplatePresetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["template"] = "template"
    display_name: str = Field(min_length=1, max_length=128)
    world_preset_id: str = Field(min_length=1, max_length=128)
    world_preset_revision: int = Field(ge=1)
    cast_preset_ids: list[str] = Field(default_factory=list, max_length=16)
    tone: str | None = Field(default=None, max_length=128)
    pacing: str | None = Field(default=None, max_length=32)


PresetPayload = Annotated[
    WorldPresetPayload | CharacterPresetPayload | StylePackPayload | TemplatePresetPayload,
    Field(discriminator="kind"),
]


class Preset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: PresetId
    kind: PresetKind
    name: str = Field(min_length=1, max_length=128)
    builtin: bool = False
    readonly: bool = False
    archived_at: datetime | None = None
    current_revision: int = Field(default=1, ge=1)
    version: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utcnow)


class PresetRevision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    preset_id: PresetId
    revision: int = Field(ge=1)
    schema_version: int = Field(default=1, ge=1)
    payload: PresetPayload
    content_hash: str = Field(min_length=1, max_length=128)
    created_at: datetime = Field(default_factory=utcnow)
