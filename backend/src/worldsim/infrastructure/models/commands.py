"""Durable command record mapping (owned by S0-DB-002).

One row per idempotency key per world: the same key with the same input
hash returns the stored result; a different hash is a conflict.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserCommandRow(Base):
    __tablename__ = "user_command"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_command_world"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128))
    actor_role: Mapped[str] = mapped_column(String(16))
    command_type: Mapped[str] = mapped_column(String(32))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    expected_versions: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    input_hash: Mapped[str] = mapped_column(String(64))
    result_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world_event.id", name="fk_command_result", use_alter=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        CheckConstraint(
            "actor_role IN ('watcher','director','deity','player','system')",
            name="ck_command_actor",
        ),
        CheckConstraint("schema_version >= 1", name="ck_command_schema"),
        UniqueConstraint("world_id", "idempotency_key", name="uq_command_world_key"),
    )
