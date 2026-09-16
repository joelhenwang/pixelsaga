"""Stage 3 long-term memory digests."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0020_s3_digests"
down_revision = "0019_s3_salience"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "long_term_memory",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_digest_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "owner_character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_digest_owner"),
            nullable=False,
            index=True,
        ),
        sa.Column("text", sa.String(4000), nullable=False),
        sa.Column("source_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("day", sa.Integer, nullable=False),
        sa.Column("created_phase_index", sa.Integer, nullable=False),
        sa.Column("profile_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("prompt_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.CheckConstraint("version >= 1", name="ck_digest_version"),
        sa.CheckConstraint("day >= 1", name="ck_digest_day"),
        sa.CheckConstraint("created_phase_index >= 0", name="ck_digest_phase"),
    )
    op.create_index("ix_digest_owner_day", "long_term_memory", ["owner_character_id", "day"])


def downgrade() -> None:
    op.drop_index("ix_digest_owner_day", table_name="long_term_memory")
    op.drop_table("long_term_memory")
