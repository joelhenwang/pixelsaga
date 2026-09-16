"""Stage 2 daily summaries."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0017_s2_summaries"
down_revision = "0016_s2_narrative"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_summary",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_summary_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "owner_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_summary_owner"),
            nullable=False,
            index=True,
        ),
        sa.Column("day", sa.Integer, nullable=False, server_default="1"),
        sa.Column("text", sa.String(4000), nullable=False),
        sa.Column("source_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("profile_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("prompt_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("fallback", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.CheckConstraint("version >= 1", name="ck_summary_version"),
    )


def downgrade() -> None:
    op.drop_table("daily_summary")
