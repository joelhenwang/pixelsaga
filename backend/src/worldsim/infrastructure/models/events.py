"""World event and effect mappings (owned by S0-DB-002)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WorldEventRow(Base):
    __tablename__ = "world_event"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_event_world"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(32))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    absolute_index: Mapped[int] = mapped_column(Integer)
    phase_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("phase_run.id", name="fk_event_run"), nullable=True
    )
    source_command_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user_command.id", name="fk_event_command"),
        nullable=True,
    )
    source_task_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("task_run.id", name="fk_event_task"), nullable=True
    )
    participant_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    summary: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    visibility: Mapped[str] = mapped_column(String(16), default="public")
    random_seed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    random_algorithm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    random_result: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        CheckConstraint("sequence >= 1", name="ck_event_sequence"),
        CheckConstraint(
            "event_type IN ('world_seeded','world_ticked','action_resolved')",
            name="ck_event_type",
        ),
        CheckConstraint("schema_version >= 1", name="ck_event_schema"),
        CheckConstraint("absolute_index >= 0", name="ck_event_index"),
        CheckConstraint("visibility IN ('public','private')", name="ck_event_visibility"),
        UniqueConstraint("world_id", "sequence", name="uq_event_world_sequence"),
    )


class EventEffectRow(Base):
    __tablename__ = "event_effect"

    event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world_event.id", name="fk_effect_event"),
        primary_key=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    effect_type: Mapped[str] = mapped_column(String(32))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        CheckConstraint("ordinal >= 0", name="ck_effect_ordinal"),
        CheckConstraint(
            "effect_type IN ('advance_clock','move_entity','resource_adjusted',"
            "'record_observation','record_memory')",
            name="ck_effect_type",
        ),
        CheckConstraint("schema_version >= 1", name="ck_effect_schema"),
    )
