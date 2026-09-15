"""World, config, clock, entity, and location mappings (owned by S0-DB-002)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
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


class WorldRow(Base):
    __tablename__ = "world"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="active")
    seed_version: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        CheckConstraint("status IN ('active', 'paused', 'ended')", name="ck_world_status"),
        CheckConstraint("version >= 0", name="ck_world_version"),
    )


class WorldConfigRow(Base):
    __tablename__ = "world_config"

    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_world_config_world"),
        primary_key=True,
    )
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)


class WorldClockRow(Base):
    __tablename__ = "world_clock"

    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_world_clock_world"), primary_key=True
    )
    day: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(16))
    absolute_index: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("day >= 1", name="ck_world_clock_day"),
        CheckConstraint(
            "phase IN ('dawn','sunrise','morning','noon','afternoon','sunset',"
            "'dusk','evening','night','midnight')",
            name="ck_world_clock_phase",
        ),
        CheckConstraint("absolute_index >= 0", name="ck_world_clock_index"),
    )


class EntityRow(Base):
    __tablename__ = "entity"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_entity_world"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    created_phase_index: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("kind IN ('character','location')", name="ck_entity_kind"),
        CheckConstraint("created_phase_index >= 0", name="ck_entity_phase"),
    )


class LocationRow(Base):
    __tablename__ = "location"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entity.id", name="fk_location_entity"), primary_key=True
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_location_world"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    region: Mapped[str] = mapped_column(String(128), default="")
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    routes: Mapped[list[object]] = mapped_column(JSONB, default=list)
    discovered: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("capacity IS NULL OR capacity >= 1", name="ck_location_capacity"),
        CheckConstraint("version >= 0", name="ck_location_version"),
        UniqueConstraint("world_id", "name", name="uq_location_world_name"),
    )
