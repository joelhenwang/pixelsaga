"""Stage 2 narrative hooks and arcs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0016_s2_narrative"
down_revision = "0015_s2_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "narrative_hook",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_hook_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(1024), nullable=False, server_default=""),
        sa.Column("requested_powers", sa.String(256), nullable=False, server_default=""),
        sa.Column("participant_ids", sa.String(1024), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_hook_version"),
    )
    op.create_table(
        "narrative_arc",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_arc_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(1024), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_arc_version"),
    )


def downgrade() -> None:
    op.drop_table("narrative_arc")
    op.drop_table("narrative_hook")
