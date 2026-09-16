"""D&D monster pool mapping (owned by DND-MONSTER)."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class MonsterRow(Base):
    __tablename__ = "dnd_monster"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_monster_world"),
        index=True,
    )
    name_key: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128))
    hp_current: Mapped[int] = mapped_column(Integer, default=0)
    hp_max: Mapped[int] = mapped_column(Integer, default=0)
    ac: Mapped[int] = mapped_column(Integer, default=10)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_monster_version"),
        CheckConstraint("hp_current >= 0", name="ck_monster_hp_current"),
        UniqueConstraint("world_id", "name_key", name="uq_monster_world_name"),
    )
