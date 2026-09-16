"""Stage 2 skills, items, and training progress."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0015_s2_progress"
down_revision = "0014_s2_knowledge"
branch_labels = None
depends_on = None


_EFFECT_TYPES = (
    "'advance_clock','move_entity','resource_adjusted',"
    "'record_observation','record_memory','skill_progress'"
)
_EFFECT_TYPES_DOWN = (
    "'advance_clock','move_entity','resource_adjusted','record_observation','record_memory'"
)


def upgrade() -> None:
    op.drop_constraint("ck_effect_type", "event_effect", type_="check")
    op.create_check_constraint(
        "ck_effect_type", "event_effect", f"effect_type IN ({_EFFECT_TYPES})"
    )
    op.create_table(
        "skill_definition",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_skill_def_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("max_progress", sa.Integer, nullable=False, server_default="100"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_skill_def_version"),
        sa.UniqueConstraint("world_id", "key", name="uq_skill_def_world_key"),
    )
    op.create_table(
        "character_skill",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_char_skill_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_char_skill_character"),
            nullable=False,
            index=True,
        ),
        sa.Column("skill_key", sa.String(64), nullable=False),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sessions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_char_skill_version"),
        sa.CheckConstraint("progress >= 0", name="ck_char_skill_progress"),
        sa.UniqueConstraint("world_id", "character_id", "skill_key", name="uq_char_skill_triple"),
    )
    op.create_table(
        "training_session",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_training_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_training_character"),
            nullable=False,
            index=True,
        ),
        sa.Column("skill_key", sa.String(64), nullable=False),
        sa.Column("session_key", sa.String(128), nullable=False),
        sa.Column("gain", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_training_version"),
        sa.UniqueConstraint(
            "world_id", "character_id", "skill_key", "session_key", name="uq_training_session"
        ),
    )
    op.create_table(
        "item_instance",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_item_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("item_key", sa.String(64), nullable=False),
        sa.Column(
            "owner_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_item_owner"),
            nullable=True,
        ),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_item_version"),
        sa.CheckConstraint("quantity >= 1", name="ck_item_quantity"),
    )


def downgrade() -> None:
    op.drop_constraint("ck_effect_type", "event_effect", type_="check")
    op.create_check_constraint(
        "ck_effect_type", "event_effect", f"effect_type IN ({_EFFECT_TYPES_DOWN})"
    )
    op.drop_table("item_instance")
    op.drop_table("training_session")
    op.drop_table("character_skill")
    op.drop_table("skill_definition")
