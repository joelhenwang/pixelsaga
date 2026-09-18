"""Versioned visual assets and provider-neutral image jobs (owned by REVAMP-P04).

Binaries live outside database rows behind a storage port; the database
holds immutable references plus lifecycle state. Fixtures complete jobs
explicitly in tests; a live provider adapter fills the same seam.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.ids import AssetId, CharacterId, ImageJobId, LocationId, WorldId


class AssetKind(StrEnum):
    MAP = "map"
    BACKGROUND = "background"
    PORTRAIT = "portrait"


class AssetStatus(StrEnum):
    READY = "ready"


class JobStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


#: Generation attempts per job before it fails terminally.
MAX_JOB_ATTEMPTS = 3


class AssetRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: AssetId
    world_id: WorldId | None = None
    kind: AssetKind
    subject_id: CharacterId | LocationId | None = None
    content_ref: str = Field(min_length=1, max_length=512)
    mime: str = Field(min_length=1, max_length=64)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    style_pack_version: str = Field(min_length=1, max_length=64)
    subject_visual_version: int = Field(default=1, ge=1)
    status: AssetStatus = AssetStatus.READY
    version: int = Field(default=0, ge=0)


class ImageJob(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ImageJobId
    world_id: WorldId | None = None
    kind: AssetKind
    subject_id: CharacterId | LocationId | None = None
    style_pack_version: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)
    status: JobStatus = JobStatus.PENDING
    attempt_count: int = Field(default=0, ge=0)
    result_asset_id: AssetId | None = None
    error: str = Field(default="", max_length=1024)
    version: int = Field(default=0, ge=0)
