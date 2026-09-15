"""Phase run, snapshot, and eligibility mappings (owned by S0-DB-002).

Snapshots are immutable: the migration installs a trigger rejecting
UPDATE and DELETE, so history cannot be rewritten behind the transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


_PHASE_RUN_STATES = (
    "'created','world_ticked','snapshot_sealed','director_complete',"
    "'intents_complete','scenes_assembled','scenes_committed',"
    "'perception_complete','post_commit_queued','completed','paused',"
    "'retryable_failed','terminal_failed','cancelled'"
)


class PhaseRunRow(Base):
    __tablename__ = "phase_run"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_phase_run_world"), index=True
    )
    absolute_index: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(32), default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        CheckConstraint("absolute_index >= 0", name="ck_phase_run_index"),
        CheckConstraint(f"state IN ({_PHASE_RUN_STATES})", name="ck_phase_run_state"),
        UniqueConstraint("world_id", "absolute_index", name="uq_phase_run_world_index"),
    )


class PhaseSnapshotRow(Base):
    __tablename__ = "phase_snapshot"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_snapshot_world"), index=True
    )
    phase_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("phase_run.id", name="fk_snapshot_run"),
        unique=True,
    )
    absolute_index: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    world_version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    sealed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        CheckConstraint("absolute_index >= 0", name="ck_snapshot_index"),
        CheckConstraint("schema_version >= 1", name="ck_snapshot_schema"),
        CheckConstraint("world_version >= 0", name="ck_snapshot_world_version"),
    )


class PhaseSnapshotCharacterRow(Base):
    __tablename__ = "phase_snapshot_character"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("phase_snapshot.id", name="fk_snapchar_snapshot"),
        primary_key=True,
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_snapchar_character"),
        primary_key=True,
    )
    version: Mapped[int] = mapped_column(Integer)

    __table_args__ = (CheckConstraint("version >= 0", name="ck_snapchar_version"),)
