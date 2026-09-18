"""Story catalog, immutable setup snapshots, drafts, and creation receipts.

One story is one runtime World: the catalog is keyed by world_id, never a
second independently selected UUID. Setup snapshots pin resolved nonsecret
values so later preset or default edits cannot silently rewrite history.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.ids import PresetId, StoryDraftId, WorldId
from worldsim.domain.time import utcnow


class SetupProvenance(StrEnum):
    CREATED = "created"
    LEGACY_UNKNOWN = "legacy_unknown"


class StoryCatalogEntry(BaseModel):
    """Application organization around a runtime World."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: WorldId
    title: str = Field(min_length=1, max_length=128)
    cover_asset_id: UUID | None = None
    created_at: datetime = Field(default_factory=utcnow)
    last_played_at: datetime | None = None
    archived_at: datetime | None = None
    metadata_version: int = Field(default=1, ge=1)


class StoryInitialSetup(BaseModel):
    """Immutable resolved creation configuration for one story."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: WorldId
    schema_version: int = Field(default=1, ge=1)
    payload: dict[str, Any]
    content_hash: str = Field(min_length=1, max_length=128)
    created_at: datetime = Field(default_factory=utcnow)
    provenance: SetupProvenance = SetupProvenance.CREATED


class DraftStep(StrEnum):
    WORLD = "world"
    CHARACTERS = "characters"
    MODE = "mode"
    STORY = "story"
    AI = "ai"
    REVIEW = "review"


class DraftWorld(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    preset_id: PresetId | None = None
    preset_revision: int | None = None
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class DraftCastMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instance_key: str = Field(min_length=1, max_length=64)
    preset_id: PresetId | None = None
    preset_revision: int | None = None
    name: str = Field(min_length=1, max_length=64)
    location_key: str | None = Field(default=None, max_length=64)


class DraftMode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(min_length=1, max_length=16)
    controlled_cast_key: str | None = Field(default=None, max_length=64)


class DraftStory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str | None = Field(default=None, max_length=128)
    premise: str | None = Field(default=None, max_length=2000)
    tone: str | None = Field(default=None, max_length=128)
    pacing: str | None = Field(default=None, max_length=32)


class DraftAi(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_revision: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    style_pack_revision: str | None = Field(default=None, max_length=128)
    art_source: str | None = Field(default=None, max_length=32)


class DraftPayload(BaseModel):
    """Typed draft JSON; secrets and binary images never belong here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    world: DraftWorld = Field(default_factory=DraftWorld)
    cast: list[DraftCastMember] = Field(default_factory=list)
    mode: DraftMode = Field(default=DraftMode(role="watcher"))
    story: DraftStory = Field(default_factory=DraftStory)
    ai: DraftAi = Field(default_factory=DraftAi)


class StoryDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: StoryDraftId
    payload: DraftPayload
    current_step: DraftStep = DraftStep.WORLD
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    created_world_id: WorldId | None = None


class StoryCreationReceipt(BaseModel):
    """Idempotent creation record: same key plus same hash replays one story."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operator: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)
    request_hash: str = Field(min_length=1, max_length=128)
    created_world_id: WorldId
    created_at: datetime = Field(default_factory=utcnow)
