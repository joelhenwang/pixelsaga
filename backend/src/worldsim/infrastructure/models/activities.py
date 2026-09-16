"""Travel and activity persistence (owned by S2-CONTRACT-001)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class ActivityRow(Base):
    __tablename__ = "activity"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_activity_world"),
        index=True,
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_activity_character"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="planned")
    start_absolute: Mapped[int] = mapped_column(Integer, default=0)
    duration_phases: Mapped[int] = mapped_column(Integer, default=1)
    progress_phases: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_activity_version"),
        CheckConstraint("duration_phases >= 1", name="ck_activity_duration"),
        CheckConstraint("progress_phases >= 0", name="ck_activity_progress"),
    )


class TravelRouteRow(Base):
    __tablename__ = "travel_route"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_route_world"),
        index=True,
    )
    from_location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("location.id", name="fk_route_from"),
    )
    to_location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("location.id", name="fk_route_to"),
    )
    duration_phases: Mapped[int] = mapped_column(Integer, default=1)
    stamina_cost: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_route_version"),
        CheckConstraint("duration_phases >= 1", name="ck_route_duration"),
        UniqueConstraint("world_id", "from_location_id", "to_location_id", name="uq_route_legs"),
    )
