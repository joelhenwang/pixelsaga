"""Observation and recent-memory mappings (owned by S0-DB-002)."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class ObservationRow(Base):
    __tablename__ = "observation"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_obs_world"), index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world_event.id", name="fk_obs_event"), index=True
    )
    observer_character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_obs_observer"),
        index=True,
    )
    facts: Mapped[list[object]] = mapped_column(JSONB, default=list)
    created_phase_index: Mapped[int] = mapped_column(Integer)
    salience: Mapped[float] = mapped_column(Float, default=1.0)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (CheckConstraint("created_phase_index >= 0", name="ck_obs_phase"),)


class RecentMemoryRow(Base):
    __tablename__ = "recent_memory"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_mem_world"), index=True
    )
    owner_character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("character.id", name="fk_mem_owner"), index=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world_event.id", name="fk_mem_event"), nullable=True
    )
    observation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("observation.id", name="fk_mem_obs"), nullable=True
    )
    text: Mapped[str] = mapped_column(String(2000))
    visibility: Mapped[str] = mapped_column(String(16), default="private")
    created_phase_index: Mapped[int] = mapped_column(Integer)
    salience: Mapped[float] = mapped_column(Float, default=1.0)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint("visibility IN ('public','private')", name="ck_mem_visibility"),
        CheckConstraint("created_phase_index >= 0", name="ck_mem_phase"),
    )
