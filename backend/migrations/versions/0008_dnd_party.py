"""D&D party roster: one row per adventurer with a versioned sheet."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0008_dnd_party"
down_revision = "0007_resolution_seed_bigint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dnd_party_member",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_party_member_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("name_key", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_party_member_character"),
            nullable=True,
        ),
        sa.Column("sheet", JSONB, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("version >= 0", name="ck_party_member_version"),
        sa.UniqueConstraint("world_id", "name_key", name="uq_party_member_world_name"),
    )


def downgrade() -> None:
    op.drop_table("dnd_party_member")
