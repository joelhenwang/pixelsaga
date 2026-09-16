"""Stage 2 claims and beliefs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0014_s2_knowledge"
down_revision = "0013_s2_relationships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "claim",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_claim_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "speaker_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_claim_speaker"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "audience_location_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("location.id", name="fk_claim_audience"),
            nullable=True,
        ),
        sa.Column("proposition", sa.String(1024), nullable=False),
        sa.Column(
            "refutes_claim_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("claim.id", name="fk_claim_refutes", use_alter=True),
            nullable=True,
        ),
        sa.Column(
            "source_event_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world_event.id", name="fk_claim_event"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_claim_version"),
    )
    op.create_table(
        "belief",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_belief_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "holder_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_belief_holder"),
            nullable=False,
            index=True,
        ),
        sa.Column("proposition", sa.String(1024), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
        sa.Column(
            "source_claim_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("claim.id", name="fk_belief_claim"),
            nullable=True,
        ),
        sa.Column("last_touched_absolute", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_belief_version"),
        sa.CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_belief_confidence"),
        sa.UniqueConstraint("world_id", "holder_id", "proposition", name="uq_belief_holding"),
    )


def downgrade() -> None:
    op.drop_table("belief")
    op.drop_table("claim")
