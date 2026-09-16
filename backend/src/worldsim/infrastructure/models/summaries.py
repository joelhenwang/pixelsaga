"""Daily summary persistence (owned by S2-SUMMARY-001)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class DailySummaryRow(Base):
    __tablename__ = "daily_summary"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_summary_world"),
        index=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_summary_owner"),
        index=True,
    )
    day: Mapped[int] = mapped_column(Integer, default=1)
    text: Mapped[str] = mapped_column(String(4000))
    source_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    profile_version: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (CheckConstraint("version >= 1", name="ck_summary_version"),)
