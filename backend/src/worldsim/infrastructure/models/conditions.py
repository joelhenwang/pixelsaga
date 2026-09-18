"""World condition mapping (owned by REVAMP-P09)."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class WorldConditionRow(Base):
    __tablename__ = "world_condition"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_condition_world"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16))
    public_label: Mapped[str] = mapped_column(String(128))
    detail: Mapped[str] = mapped_column(String(1024), default="")
    scope_location_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)))
    severity: Mapped[int] = mapped_column(Integer)
    started_absolute: Mapped[int] = mapped_column(Integer)
    ends_absolute: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="active")
    source_intervention_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, default=None
    )
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_condition_version"),
        CheckConstraint("severity BETWEEN 1 AND 5", name="ck_condition_severity"),
    )
