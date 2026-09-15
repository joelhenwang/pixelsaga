"""Character identity, card, and state mappings (owned by S0-DB-002)."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class CharacterRow(Base):
    __tablename__ = "character"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entity.id", name="fk_character_entity"), primary_key=True
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_character_world"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))


class CharacterCardVersionRow(Base):
    __tablename__ = "character_card_version"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_card_character"),
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(128))
    appearance: Mapped[str] = mapped_column(String(2000), default="")
    personality: Mapped[str] = mapped_column(String(2000), default="")
    background: Mapped[str] = mapped_column(String(2000), default="")

    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_card_version"),
        UniqueConstraint("character_id", "version", name="uq_card_character_version"),
    )


class CharacterStateRow(Base):
    __tablename__ = "character_state"

    character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_state_character"),
        primary_key=True,
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_state_world"), index=True
    )
    card_version: Mapped[int] = mapped_column(Integer)
    life_status: Mapped[str] = mapped_column(String(16), default="alive")
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("location.id", name="fk_state_location"), index=True
    )
    stamina: Mapped[int] = mapped_column(Integer)
    mana: Mapped[int] = mapped_column(Integer)
    conditions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("card_version >= 1", name="ck_state_card_version"),
        CheckConstraint("life_status IN ('alive','dead')", name="ck_state_life"),
        CheckConstraint("stamina BETWEEN 0 AND 100", name="ck_state_stamina"),
        CheckConstraint("mana BETWEEN 0 AND 100", name="ck_state_mana"),
        CheckConstraint("version >= 0", name="ck_state_version"),
    )
