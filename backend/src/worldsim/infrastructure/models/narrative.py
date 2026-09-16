"""Narrative hook and arc persistence (owned by S2-DIRECTOR-001)."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class NarrativeHookRow(Base):
    __tablename__ = "narrative_hook"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_hook_world"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(128))
    purpose: Mapped[str] = mapped_column(String(1024), default="")
    requested_powers: Mapped[str] = mapped_column(String(256), default="")
    participant_ids: Mapped[str] = mapped_column(String(1024), default="")
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (CheckConstraint("version >= 0", name="ck_hook_version"),)


class NarrativeArcRow(Base):
    __tablename__ = "narrative_arc"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_arc_world"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(128))
    purpose: Mapped[str] = mapped_column(String(1024), default="")
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (CheckConstraint("version >= 0", name="ck_arc_version"),)
