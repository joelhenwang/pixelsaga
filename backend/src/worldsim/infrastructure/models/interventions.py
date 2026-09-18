"""Intervention queue mapping (owned by REVAMP-P07)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class InterventionRow(Base):
    __tablename__ = "intervention"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_intervention_world"),
        index=True,
    )
    client_request_id: Mapped[str] = mapped_column(String(128))
    text: Mapped[str] = mapped_column(String(2000))
    mode: Mapped[str] = mapped_column(String(16))
    role: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    interpretation: Mapped[dict[str, Any]] = mapped_column(JSONB)
    context_watermark: Mapped[int] = mapped_column(Integer, default=0)
    prompt_version: Mapped[str] = mapped_column(String(64), default="intervene-v1")
    failure_reason: Mapped[str] = mapped_column(String(1024), default="")
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_intervention_version"),
        UniqueConstraint("world_id", "client_request_id", name="uq_intervention_world_key"),
    )


class InterventionStepRow(Base):
    __tablename__ = "intervention_step"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    intervention_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("intervention.id", name="fk_step_intervention"),
        index=True,
    )
    seq: Mapped[int] = mapped_column(Integer)
    step_key: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))
    targets: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    result_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, default=None
    )
    result_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, default=None
    )
    result_hook_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, default=None
    )
    failure_reason: Mapped[str] = mapped_column(String(1024), default="")
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_step_version"),
        UniqueConstraint("intervention_id", "seq", name="uq_step_intervention_seq"),
        UniqueConstraint("step_key", name="uq_step_key"),
    )
