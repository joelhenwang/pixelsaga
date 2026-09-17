"""Macro simulation and genealogy persistence (owned by S5-CONTRACT-001)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class MacroPeriodRunRow(Base):
    __tablename__ = "macro_period_run"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_macro_run_world"),
        index=True,
    )
    start_absolute: Mapped[int] = mapped_column(Integer, nullable=False)
    end_absolute: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="planned")
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("end_absolute > start_absolute", name="ck_macro_run_range"),
        CheckConstraint("version >= 0", name="ck_macro_run_version"),
        UniqueConstraint(
            "world_id", "start_absolute", "end_absolute", "resolution", name="uq_macro_run_period"
        ),
    )


class MacroAggregateEffectRow(Base):
    __tablename__ = "macro_aggregate_effect"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("macro_period_run.id", name="fk_macro_effect_run"),
        index=True,
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_macro_effect_world"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    detail: Mapped[str] = mapped_column(String(2000))
    event_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class MacroInterruptionRow(Base):
    __tablename__ = "macro_interruption"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("macro_period_run.id", name="fk_macro_interrupt_run"),
        index=True,
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_macro_interrupt_world"),
        index=True,
    )
    at_absolute: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[str] = mapped_column(String(2000))


class LineageLinkRow(Base):
    __tablename__ = "lineage_link"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_lineage_world"),
        index=True,
    )
    parent_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_lineage_parent"),
        index=True,
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_lineage_child"),
        index=True,
    )
    birth_absolute: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("parent_id != child_id", name="ck_lineage_distinct"),
        UniqueConstraint("world_id", "parent_id", "child_id", name="uq_lineage_link"),
    )


class LineageCharacterRow(Base):
    __tablename__ = "lineage_character"

    character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_lineage_char_character"),
        primary_key=True,
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_lineage_char_world"),
        index=True,
    )
    birth_absolute: Mapped[int] = mapped_column(Integer, nullable=False)
    death_absolute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    life_status: Mapped[str] = mapped_column(String(16), nullable=False, default="alive")
    succession_eligible: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        CheckConstraint(
            "death_absolute IS NULL OR death_absolute >= birth_absolute",
            name="ck_lineage_char_death",
        ),
    )


class FocusAssignmentRow(Base):
    __tablename__ = "focus_assignment"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_focus_world"),
        index=True,
    )
    slot: Mapped[str] = mapped_column(String(16), nullable=False)
    from_character_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_focus_from"),
        nullable=True,
    )
    to_character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_focus_to"),
        index=True,
    )
    effective_absolute: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (CheckConstraint("version >= 0", name="ck_focus_version"),)


class EraSummaryRow(Base):
    __tablename__ = "era_summary"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_era_world"),
        index=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_era_owner"),
        index=True,
    )
    start_absolute: Mapped[int] = mapped_column(Integer, nullable=False)
    end_absolute: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String(8000))
    source_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    profile_version: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        CheckConstraint("end_absolute > start_absolute", name="ck_era_range"),
        CheckConstraint("version >= 1", name="ck_era_version"),
    )


class EndConditionEvidenceRow(Base):
    __tablename__ = "end_condition_evidence"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_end_world"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluated_absolute: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start_absolute: Mapped[int] = mapped_column(Integer, nullable=False)
    satisfied: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_event_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    detail: Mapped[str] = mapped_column(String(2000))

    __table_args__ = (
        CheckConstraint(
            "window_start_absolute <= evaluated_absolute",
            name="ck_end_window",
        ),
    )
