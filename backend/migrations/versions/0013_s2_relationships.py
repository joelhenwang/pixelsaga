"""Stage 2 relationship evidence and projection."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0013_s2_relationships"
down_revision = "0012_s2_schedules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "relationship_evidence",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_rel_evidence_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "source_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_rel_evidence_source"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "target_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_rel_evidence_target"),
            nullable=False,
            index=True,
        ),
        sa.Column("dimension", sa.String(16), nullable=False),
        sa.Column("delta", sa.Integer, nullable=False, server_default="0"),
        sa.Column("note", sa.String(512), nullable=False, server_default=""),
        sa.Column(
            "source_event_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world_event.id", name="fk_rel_evidence_event"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_rel_evidence_version"),
        sa.CheckConstraint("delta >= -10 AND delta <= 10", name="ck_rel_evidence_delta"),
    )
    op.create_table(
        "relationship",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_relationship_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "source_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_relationship_source"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_relationship_target"),
            nullable=False,
        ),
        sa.Column("trust", sa.Integer, nullable=False, server_default="0"),
        sa.Column("affection", sa.Integer, nullable=False, server_default="0"),
        sa.Column("respect", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_relationship_version"),
        sa.UniqueConstraint("world_id", "source_id", "target_id", name="uq_relationship_pair"),
    )


def downgrade() -> None:
    op.drop_table("relationship")
    op.drop_table("relationship_evidence")
