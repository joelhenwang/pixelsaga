"""Claim and belief persistence (owned by S2-KNOW-001)."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class ClaimRow(Base):
    __tablename__ = "claim"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_claim_world"),
        index=True,
    )
    speaker_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_claim_speaker"),
        index=True,
    )
    audience_location_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("location.id", name="fk_claim_audience"),
        nullable=True,
        default=None,
    )
    proposition: Mapped[str] = mapped_column(String(1024))
    refutes_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("claim.id", name="fk_claim_refutes", use_alter=True),
        nullable=True,
        default=None,
    )
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world_event.id", name="fk_claim_event"),
        nullable=True,
        default=None,
    )
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (CheckConstraint("version >= 0", name="ck_claim_version"),)


class BeliefRow(Base):
    __tablename__ = "belief"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_belief_world"),
        index=True,
    )
    holder_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_belief_holder"),
        index=True,
    )
    proposition: Mapped[str] = mapped_column(String(1024))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("claim.id", name="fk_belief_claim"),
        nullable=True,
        default=None,
    )
    last_touched_absolute: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_belief_version"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_belief_confidence"),
        UniqueConstraint("world_id", "holder_id", "proposition", name="uq_belief_holding"),
    )
