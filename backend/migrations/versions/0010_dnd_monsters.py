"""D&D monster pools persist across scenes (one live pool per key)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0010_dnd_monsters"
down_revision = "0009_event_seed_bigint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dnd_monster",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_monster_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("name_key", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("hp_current", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hp_max", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ac", sa.Integer, nullable=False, server_default="10"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_monster_version"),
        sa.CheckConstraint("hp_current >= 0", name="ck_monster_hp_current"),
        sa.UniqueConstraint("world_id", "name_key", name="uq_monster_world_name"),
    )


def downgrade() -> None:
    op.drop_table("dnd_monster")
