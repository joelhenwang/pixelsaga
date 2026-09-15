"""Model profile, call, and context-manifest mappings (owned by S0-DB-002).

Durable audit for every model interaction; disabling external tracing
never removes these rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ModelProfileRow(Base):
    __tablename__ = "model_profile"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    adapter: Mapped[str] = mapped_column(String(16))
    model_id: Mapped[str] = mapped_column(String(128))
    max_context_tokens: Mapped[int] = mapped_column(Integer)
    capabilities: Mapped[list[str]] = mapped_column(JSONB, default=list)

    __table_args__ = (
        CheckConstraint("adapter IN ('fake','openrouter')", name="ck_profile_adapter"),
        CheckConstraint("max_context_tokens >= 1", name="ck_profile_context"),
    )


class ModelCallRow(Base):
    __tablename__ = "model_call"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_call_world"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False, server_default="unspecified")
    phase_run_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    task_run_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    profile_name: Mapped[str] = mapped_column(String(64))
    profile_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="started")
    request: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    result: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        ForeignKeyConstraint(
            ["profile_name", "profile_version"],
            ["model_profile.name", "model_profile.version"],
            name="fk_call_profile",
        ),
        CheckConstraint("status IN ('started','succeeded','failed')", name="ck_call_status"),
        CheckConstraint("prompt_tokens >= 0", name="ck_call_prompt_tokens"),
        CheckConstraint("completion_tokens >= 0", name="ck_call_completion_tokens"),
        CheckConstraint("latency_ms >= 0", name="ck_call_latency"),
    )


class ContextManifestRow(Base):
    __tablename__ = "context_manifest"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("model_call.id", name="fk_manifest_call"),
        unique=True,
    )
    world_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_manifest_world"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False, server_default="unspecified")
    profile_name: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    profile_version: Mapped[str] = mapped_column(String(32), nullable=False, server_default="")
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    rendered_hash: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    sources: Mapped[list[object]] = mapped_column(JSONB, default=list)
    budgets: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    tokens: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    dropped: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
