"""Stage 2 schedules persist across ticks."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0012_s2_schedules"
down_revision = "0011_s2_activity_route_focus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_event_type", "world_event", type_="check")
    op.create_check_constraint(
        "ck_event_type",
        "world_event",
        "event_type IN ('world_seeded','world_ticked','action_resolved','schedule_fired')",
    )
    op.create_table(
        "scheduled_effect",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_schedule_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("due_absolute", sa.Integer, nullable=False, server_default="0"),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_schedule_version"),
        sa.CheckConstraint("due_absolute >= 0", name="ck_schedule_due"),
    )


def downgrade() -> None:
    op.drop_table("scheduled_effect")
    op.drop_constraint("ck_event_type", "world_event", type_="check")
    op.create_check_constraint(
        "ck_event_type",
        "world_event",
        "event_type IN ('world_seeded','world_ticked','action_resolved')",
    )
