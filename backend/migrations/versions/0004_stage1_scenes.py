"""Stage 1 scene records: intents, scenes, attempts, reactions, resolutions, narration."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0004_stage1_scenes"
down_revision = "0003_trace_correlation"
branch_labels = None
depends_on = None

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


def _stamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "character_intent",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_intent_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "snapshot_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("phase_snapshot.id", name="fk_intent_snapshot"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "phase_run_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("phase_run.id", name="fk_intent_run"),
            nullable=True,
        ),
        sa.Column(
            "author_character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_intent_author"),
            nullable=False,
            index=True,
        ),
        sa.Column("family", sa.String(32), nullable=False),
        sa.Column("intent", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        *_stamps(),
        sa.CheckConstraint(f"status IN ({_INTENT_STATES})", name="ck_intent_status"),
        sa.UniqueConstraint("world_id", "idempotency_key", name="uq_intent_world_key"),
        sa.UniqueConstraint(
            "world_id",
            "snapshot_id",
            "author_character_id",
            name="uq_intent_world_snapshot_author",
        ),
    )
    op.create_table(
        "scene",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_scene_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "phase_run_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("phase_run.id", name="fk_scene_run"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "snapshot_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("phase_snapshot.id", name="fk_scene_snapshot"),
            nullable=False,
            index=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="proposed"),
        sa.Column("beat_budget", sa.Integer, nullable=False, server_default="8"),
        sa.Column(
            "event_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world_event.id", name="fk_scene_event"),
            nullable=True,
            unique=True,
        ),
        *_stamps(),
        sa.CheckConstraint(f"status IN ({_SCENE_STATES})", name="ck_scene_status"),
        sa.CheckConstraint("beat_budget BETWEEN 1 AND 64", name="ck_scene_beat_budget"),
    )
    op.create_table(
        "scene_participant",
        sa.Column(
            "scene_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("scene.id", name="fk_participant_scene"),
            primary_key=True,
        ),
        sa.Column(
            "character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_participant_character"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.CheckConstraint(f"role IN ({_PARTICIPANT_ROLES})", name="ck_participant_role"),
    )
    op.create_table(
        "attempt",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_attempt_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "scene_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("scene.id", name="fk_attempt_scene"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "intent_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character_intent.id", name="fk_attempt_intent"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "actor_character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_attempt_actor"),
            nullable=False,
        ),
        sa.Column("observable_summary", sa.String(512), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({_ATTEMPT_STATES})", name="ck_attempt_status"),
    )
    op.create_table(
        "reaction",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_reaction_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "attempt_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("attempt.id", name="fk_reaction_attempt"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "scene_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("scene.id", name="fk_reaction_scene"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "reactor_character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_reaction_reactor"),
            nullable=False,
        ),
        sa.Column("reaction", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({_REACTION_STATES})", name="ck_reaction_status"),
        sa.UniqueConstraint(
            "attempt_id", "reactor_character_id", name="uq_reaction_attempt_reactor"
        ),
    )
    op.create_table(
        "resolution",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_resolution_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "scene_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("scene.id", name="fk_resolution_scene"),
            nullable=False,
            unique=True,
        ),
        sa.Column("resolver", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("profile_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("effects", JSONB, nullable=False, server_default="[]"),
        sa.Column("rationale", sa.String(2000), nullable=False, server_default=""),
        sa.Column("random_seed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"resolver IN ({_RESOLVERS})", name="ck_resolution_resolver"),
        sa.CheckConstraint(f"outcome IN ({_OUTCOMES})", name="ck_resolution_outcome"),
        sa.CheckConstraint("random_seed >= 0", name="ck_resolution_seed"),
    )
    op.create_table(
        "narration",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_narration_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "scene_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("scene.id", name="fk_narration_scene"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "event_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world_event.id", name="fk_narration_event"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "speaker_character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_narration_speaker"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.String(2000), nullable=False),
        sa.Column("emotion_hint", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_effect_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"kind IN ({_NARRATION_KINDS})", name="ck_narration_kind"),
    )


def downgrade() -> None:
    for table in (
        "narration",
        "resolution",
        "reaction",
        "attempt",
        "scene_participant",
        "scene",
        "character_intent",
    ):
        op.drop_table(table)
