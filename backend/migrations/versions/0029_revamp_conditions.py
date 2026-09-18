"""Revamp persistent world-condition table plus condition tick event type."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029_revamp_conditions"
down_revision = "0028_revamp_interventions"
branch_labels = None
depends_on = None

_EVENT_TYPES = (
    "'world_seeded','world_ticked','macro_ticked','action_resolved',"
    "'schedule_fired','deity_override','world_ended','condition_tick'"
)
_EVENT_TYPES_DOWN = (
    "'world_seeded','world_ticked','macro_ticked','action_resolved',"
    "'schedule_fired','deity_override','world_ended'"
)


def upgrade() -> None:
    op.create_table(
        "world_condition",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("world_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("public_label", sa.String(length=128), nullable=False),
        sa.Column("detail", sa.String(length=1024), nullable=False),
        sa.Column(
            "scope_location_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("started_absolute", sa.Integer(), nullable=False),
        sa.Column("ends_absolute", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_intervention_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version >= 0", name="ck_condition_version"),
        sa.CheckConstraint("severity BETWEEN 1 AND 5", name="ck_condition_severity"),
        sa.ForeignKeyConstraint(["world_id"], ["world.id"], name="fk_condition_world"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_condition_world", "world_condition", ["world_id"])
    op.drop_constraint("ck_event_type", "world_event", type_="check")
    op.create_check_constraint("ck_event_type", "world_event", f"event_type IN ({_EVENT_TYPES})")


def downgrade() -> None:
    op.drop_constraint("ck_event_type", "world_event", type_="check")
    op.create_check_constraint(
        "ck_event_type", "world_event", f"event_type IN ({_EVENT_TYPES_DOWN})"
    )
    op.drop_index("ix_condition_world", table_name="world_condition")
    op.drop_table("world_condition")
