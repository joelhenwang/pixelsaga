"""Provider connections, profile revisions, and preferences mapping."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class ProviderConnectionRow(Base):
    __tablename__ = "provider_connection"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    adapter: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))
    endpoint: Mapped[str] = mapped_column(String(512))
    credential_env: Mapped[str | None] = mapped_column(String(128))
    allow_local_endpoint: Mapped[bool] = mapped_column(Boolean, default=False)
    config_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("config_version >= 0", name="ck_connection_config_version"),
    )


class ProviderProfileRevisionRow(Base):
    __tablename__ = "provider_profile_revision"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("provider_connection.id", name="fk_profile_connection"),
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[str] = mapped_column(String(128))
    temperature: Mapped[float | None] = mapped_column(Float)
    top_p: Mapped[float | None] = mapped_column(Float)
    top_k: Mapped[int | None] = mapped_column(Integer)
    max_tokens: Mapped[int] = mapped_column(Integer, default=512)
    capabilities: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_profile_revision_number"),
        CheckConstraint("max_tokens BETWEEN 1 AND 4096", name="ck_profile_max_tokens"),
    )


class ApplicationPreferencesRow(Base):
    __tablename__ = "application_preferences"

    operator: Mapped[str] = mapped_column(String(64), primary_key=True)
    gameplay: Mapped[dict[str, Any]] = mapped_column(JSONB)
    accessibility: Mapped[dict[str, Any]] = mapped_column(JSONB)
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (CheckConstraint("version >= 0", name="ck_prefs_version"),)
