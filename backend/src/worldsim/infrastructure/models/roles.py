"""Role grant persistence (owned by S2-ROLE-001)."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class RoleGrantRow(Base):
    __tablename__ = "role_grant"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_grant_world"),
        unique=True,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16))
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_grant_character"),
        nullable=True,
        default=None,
    )
    granted_absolute: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (CheckConstraint("version >= 0", name="ck_grant_version"),)
