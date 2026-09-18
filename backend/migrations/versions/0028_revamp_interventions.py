"""Revamp durable intervention queue tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028_revamp_interventions"
down_revision = "0027_revamp_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intervention",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("world_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_request_id", sa.String(length=128), nullable=False),
        sa.Column("text", sa.String(length=2000), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("interpretation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("context_watermark", sa.Integer(), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("failure_reason", sa.String(length=1024), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version >= 0", name="ck_intervention_version"),
        sa.ForeignKeyConstraint(["world_id"], ["world.id"], name="fk_intervention_world"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("world_id", "client_request_id", name="uq_intervention_world_key"),
    )
    op.create_index("ix_intervention_world", "intervention", ["world_id"])
    op.create_table(
        "intervention_step",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("intervention_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("step_key", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("targets", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_activity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_hook_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=1024), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version >= 0", name="ck_step_version"),
        sa.ForeignKeyConstraint(
            ["intervention_id"], ["intervention.id"], name="fk_step_intervention"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("intervention_id", "seq", name="uq_step_intervention_seq"),
        sa.UniqueConstraint("step_key", name="uq_step_key"),
    )
    op.create_index("ix_step_intervention", "intervention_step", ["intervention_id"])


def downgrade() -> None:
    op.drop_index("ix_step_intervention", table_name="intervention_step")
    op.drop_table("intervention_step")
    op.drop_index("ix_intervention_world", table_name="intervention")
    op.drop_table("intervention")
