"""Revamp visual asset and image-job tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027_revamp_assets"
down_revision = "0026_s5_event_absolute_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("world_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content_ref", sa.String(length=512), nullable=False),
        sa.Column("mime", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("style_pack_version", sa.String(length=64), nullable=False),
        sa.Column("subject_visual_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version >= 0", name="ck_asset_version"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("world_id", "content_ref", name="uq_asset_world_ref"),
    )
    op.create_index("ix_asset_world", "asset_record", ["world_id"])
    op.create_table(
        "image_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("world_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("style_pack_version", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("result_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error", sa.String(length=1024), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("attempt_count >= 0", name="ck_job_attempts"),
        sa.CheckConstraint("version >= 0", name="ck_job_version"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("world_id", "idempotency_key", name="uq_job_world_key"),
    )
    op.create_index("ix_job_world", "image_job", ["world_id"])


def downgrade() -> None:
    op.drop_index("ix_job_world", table_name="image_job")
    op.drop_table("image_job")
    op.drop_index("ix_asset_world", table_name="asset_record")
    op.drop_table("asset_record")
