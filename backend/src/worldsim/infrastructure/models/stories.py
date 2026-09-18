"""Story catalog, setup snapshots, drafts, presets, and receipts mapping."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class StoryCatalogRow(Base):
    __tablename__ = "story_catalog"

    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_catalog_world"),
        primary_key=True,
    )
    title: Mapped[str] = mapped_column(String(128))
    cover_asset_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_version: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        CheckConstraint("metadata_version >= 1", name="ck_catalog_metadata_version"),
    )


class StoryInitialSetupRow(Base):
    __tablename__ = "story_initial_setup"

    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_setup_world"),
        primary_key=True,
    )
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[str] = mapped_column(String(32))

    __table_args__ = (
        CheckConstraint("schema_version >= 1", name="ck_setup_schema_version"),
    )


class StoryDraftRow(Base):
    __tablename__ = "story_draft"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    current_step: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_world_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_draft_created_world"),
        index=True,
    )

    __table_args__ = (CheckConstraint("version >= 1", name="ck_draft_version"),)


class PresetRow(Base):
    __tablename__ = "preset"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    readonly: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("current_revision >= 1", name="ck_preset_revision"),
        CheckConstraint("version >= 0", name="ck_preset_version"),
    )


class PresetRevisionRow(Base):
    __tablename__ = "preset_revision"

    preset_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("preset.id", name="fk_revision_preset"),
        primary_key=True,
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("revision >= 1", name="ck_revision_number"),)


class StoryCreationReceiptRow(Base):
    __tablename__ = "story_creation_receipt"

    operator: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(128))
    created_world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_receipt_world"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
