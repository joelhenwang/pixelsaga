"""Long-term memory digest mappings (owned by S3-MEM-001)."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class DigestRow(Base):
    __tablename__ = "long_term_memory"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_digest_world"), index=True
    )
    owner_character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_digest_owner"),
        index=True,
    )
    text: Mapped[str] = mapped_column(String(4000))
    source_ids: Mapped[list[object]] = mapped_column(JSONB, default=list)
    day: Mapped[int] = mapped_column(Integer)
    created_phase_index: Mapped[int] = mapped_column(Integer)
    profile_version: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_digest_version"),
        CheckConstraint("day >= 1", name="ck_digest_day"),
        CheckConstraint("created_phase_index >= 0", name="ck_digest_phase"),
    )
