"""Stage 2 role grants and deity override event type."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0018_s2_roles"
down_revision = "0017_s2_summaries"
branch_labels = None
depends_on = None

_EVENT_TYPES = "'world_seeded','world_ticked','action_resolved','schedule_fired','deity_override'"
_EVENT_TYPES_DOWN = "'world_seeded','world_ticked','action_resolved','schedule_fired'"
_EFFECT_TYPES = (
    "'advance_clock','move_entity','resource_adjusted',"
    "'record_observation','record_memory','skill_progress','deity_override'"
)
_EFFECT_TYPES_DOWN = (
    "'advance_clock','move_entity','resource_adjusted',"
    "'record_observation','record_memory','skill_progress'"
)


def upgrade() -> None:
    op.create_table(
        "role_grant",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_grant_world"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column(
            "character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_grant_character"),
            nullable=True,
        ),
        sa.Column("granted_absolute", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_grant_version"),
    )
    op.drop_constraint("ck_event_type", "world_event", type_="check")
    op.create_check_constraint("ck_event_type", "world_event", f"event_type IN ({_EVENT_TYPES})")
    op.drop_constraint("ck_effect_type", "event_effect", type_="check")
    op.create_check_constraint(
        "ck_effect_type", "event_effect", f"effect_type IN ({_EFFECT_TYPES})"
    )


def downgrade() -> None:
    op.drop_constraint("ck_effect_type", "event_effect", type_="check")
    op.create_check_constraint(
        "ck_effect_type", "event_effect", f"effect_type IN ({_EFFECT_TYPES_DOWN})"
    )
    op.drop_constraint("ck_event_type", "world_event", type_="check")
    op.create_check_constraint(
        "ck_event_type", "world_event", f"event_type IN ({_EVENT_TYPES_DOWN})"
    )
    op.drop_table("role_grant")
