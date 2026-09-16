"""Skill and item-instance persistence (owned by S2-PROGRESS-001)."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class SkillDefinitionRow(Base):
    __tablename__ = "skill_definition"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_skill_def_world"),
        index=True,
    )
    key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    max_progress: Mapped[int] = mapped_column(Integer, default=100)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_skill_def_version"),
        UniqueConstraint("world_id", "key", name="uq_skill_def_world_key"),
    )


class CharacterSkillRow(Base):
    __tablename__ = "character_skill"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_char_skill_world"),
        index=True,
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_char_skill_character"),
        index=True,
    )
    skill_key: Mapped[str] = mapped_column(String(64))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    sessions: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_char_skill_version"),
        CheckConstraint("progress >= 0", name="ck_char_skill_progress"),
        UniqueConstraint("world_id", "character_id", "skill_key", name="uq_char_skill_triple"),
    )


class TrainingSessionRow(Base):
    __tablename__ = "training_session"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_training_world"),
        index=True,
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_training_character"),
        index=True,
    )
    skill_key: Mapped[str] = mapped_column(String(64))
    session_key: Mapped[str] = mapped_column(String(128))
    gain: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_training_version"),
        UniqueConstraint(
            "world_id",
            "character_id",
            "skill_key",
            "session_key",
            name="uq_training_session",
        ),
    )


class ItemInstanceRow(Base):
    __tablename__ = "item_instance"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_item_world"),
        index=True,
    )
    item_key: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_item_owner"),
        nullable=True,
        default=None,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_item_version"),
        CheckConstraint("quantity >= 1", name="ck_item_quantity"),
    )
