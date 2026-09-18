"""Application settings tables: provider connections, profile revisions, prefs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031_settings_pipeline"
down_revision = "0030_application_shell"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_connection",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("adapter", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("endpoint", sa.String(length=512), nullable=False),
        sa.Column("credential_env", sa.String(length=128), nullable=True),
        sa.Column("allow_local_endpoint", sa.Boolean(), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("config_version >= 0", name="ck_connection_config_version"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "provider_profile_revision",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("top_p", sa.Float(), nullable=True),
        sa.Column("top_k", sa.Integer(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_profile_revision_number"),
        sa.CheckConstraint("max_tokens BETWEEN 1 AND 4096", name="ck_profile_max_tokens"),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["provider_connection.id"], name="fk_profile_connection"
        ),
        sa.PrimaryKeyConstraint("id", "revision"),
    )
    op.create_index("ix_profile_connection", "provider_profile_revision", ["connection_id"])
    op.create_table(
        "application_preferences",
        sa.Column("operator", sa.String(length=64), nullable=False),
        sa.Column("gameplay", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("accessibility", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("profile", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version >= 0", name="ck_prefs_version"),
        sa.PrimaryKeyConstraint("operator"),
    )


def downgrade() -> None:
    op.drop_table("application_preferences")
    op.drop_index("ix_profile_connection", table_name="provider_profile_revision")
    op.drop_table("provider_profile_revision")
    op.drop_table("provider_connection")
