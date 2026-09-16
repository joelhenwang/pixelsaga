"""Intent, scene, attempt, reaction, resolution, and narration mappings.

Owned by S1-CONTRACT-001. Operational scene state lives here before
canon; only the committed world event and its effects establish facts.
Adapters and ports arrive with the owning consumer tasks.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base

_INTENT_STATES = "'proposed','validated','invalid','superseded'"
_ATTEMPT_STATES = "'pending','committed','superseded'"
_SCENE_STATES = (
    "'proposed','validating','ready','resolving','resolved','committed',"
    "'invalid','retryable_failed','terminal_failed'"
)
_REACTION_STATES = "'pending','committed'"
_RESOLVERS = "'deterministic','model'"
_OUTCOMES = "'success','partial','failure','impossible'"
_NARRATION_KINDS = "'narration','dialogue','action','system','transition'"
_PARTICIPANT_ROLES = "'initiator','reactor','observer'"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CharacterIntentRow(Base):
    __tablename__ = "character_intent"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_intent_world"), index=True
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("phase_snapshot.id", name="fk_intent_snapshot"),
        index=True,
    )
    phase_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("phase_run.id", name="fk_intent_run"), nullable=True
    )
    author_character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_intent_author"),
        index=True,
    )
    family: Mapped[str] = mapped_column(String(32))
    intent: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    idempotency_key: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        CheckConstraint(f"status IN ({_INTENT_STATES})", name="ck_intent_status"),
        UniqueConstraint("world_id", "idempotency_key", name="uq_intent_world_key"),
        UniqueConstraint(
            "world_id",
            "snapshot_id",
            "author_character_id",
            name="uq_intent_world_snapshot_author",
        ),
    )


class SceneRow(Base):
    __tablename__ = "scene"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_scene_world"), index=True
    )
    phase_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("phase_run.id", name="fk_scene_run"), index=True
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("phase_snapshot.id", name="fk_scene_snapshot"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="proposed")
    beat_budget: Mapped[int] = mapped_column(Integer, default=8)
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world_event.id", name="fk_scene_event"),
        nullable=True,
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        CheckConstraint(f"status IN ({_SCENE_STATES})", name="ck_scene_status"),
        CheckConstraint("beat_budget BETWEEN 1 AND 64", name="ck_scene_beat_budget"),
    )


class SceneParticipantRow(Base):
    __tablename__ = "scene_participant"

    scene_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("scene.id", name="fk_participant_scene"),
        primary_key=True,
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_participant_character"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(16))

    __table_args__ = (
        CheckConstraint(f"role IN ({_PARTICIPANT_ROLES})", name="ck_participant_role"),
    )


class AttemptRow(Base):
    __tablename__ = "attempt"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_attempt_world"), index=True
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("scene.id", name="fk_attempt_scene"),
        nullable=True,
        index=True,
    )
    intent_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character_intent.id", name="fk_attempt_intent"),
        unique=True,
    )
    actor_character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("character.id", name="fk_attempt_actor")
    )
    observable_summary: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (CheckConstraint(f"status IN ({_ATTEMPT_STATES})", name="ck_attempt_status"),)


class ReactionRow(Base):
    __tablename__ = "reaction"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_reaction_world"), index=True
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("attempt.id", name="fk_reaction_attempt"),
        index=True,
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("scene.id", name="fk_reaction_scene"),
        nullable=True,
        index=True,
    )
    reactor_character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("character.id", name="fk_reaction_reactor")
    )
    reaction: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        CheckConstraint(f"status IN ({_REACTION_STATES})", name="ck_reaction_status"),
        UniqueConstraint("attempt_id", "reactor_character_id", name="uq_reaction_attempt_reactor"),
    )


class ResolutionRow(Base):
    __tablename__ = "resolution"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_resolution_world"), index=True
    )
    scene_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("scene.id", name="fk_resolution_scene"), unique=True
    )
    resolver: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(16))
    profile_version: Mapped[str] = mapped_column(String(64), default="")
    effects: Mapped[list[object]] = mapped_column(JSONB, default=list)
    rationale: Mapped[str] = mapped_column(String(2000), default="")
    random_seed: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        CheckConstraint(f"resolver IN ({_RESOLVERS})", name="ck_resolution_resolver"),
        CheckConstraint(f"outcome IN ({_OUTCOMES})", name="ck_resolution_outcome"),
        CheckConstraint("random_seed >= 0", name="ck_resolution_seed"),
    )


class NarrationRow(Base):
    __tablename__ = "narration"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_narration_world"), index=True
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("scene.id", name="fk_narration_scene"),
        nullable=True,
        index=True,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world_event.id", name="fk_narration_event"), index=True
    )
    speaker_character_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_narration_speaker"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(String(2000))
    emotion_hint: Mapped[str] = mapped_column(String(128), default="")
    source_effect_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    cited_fact_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (CheckConstraint(f"kind IN ({_NARRATION_KINDS})", name="ck_narration_kind"),)
