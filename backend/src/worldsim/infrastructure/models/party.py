"""D&D party roster mapping (owned by DND-WIRE)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class PartyMemberRow(Base):
    __tablename__ = "dnd_party_member"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_party_member_world"),
        index=True,
    )
    name_key: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128))
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_party_member_character"),
        nullable=True,
        default=None,
    )
    focus_slot: Mapped[str] = mapped_column(String(16), default="companion")
    sheet: Mapped[dict[str, Any]] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_party_member_version"),
        UniqueConstraint("world_id", "name_key", name="uq_party_member_world_name"),
    )
