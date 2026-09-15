"""Trace correlation columns: role and phase/task/actor links on model_call,
plus role, profile, prompt version, and rendered hash on context_manifest.

Nullable correlation IDs carry no foreign keys: the audit chain joins
without coupling trace retention to canonical tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0003_trace_correlation"
down_revision = "0002_stage0_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_call",
        sa.Column("role", sa.String(64), nullable=False, server_default="unspecified"),
    )
    op.add_column("model_call", sa.Column("phase_run_id", PG_UUID(as_uuid=True), nullable=True))
    op.add_column("model_call", sa.Column("task_run_id", PG_UUID(as_uuid=True), nullable=True))
    op.add_column("model_call", sa.Column("actor_id", PG_UUID(as_uuid=True), nullable=True))
    op.add_column(
        "model_call",
        sa.Column("prompt_hash", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "context_manifest",
        sa.Column("role", sa.String(64), nullable=False, server_default="unspecified"),
    )
    op.add_column(
        "context_manifest",
        sa.Column("profile_name", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "context_manifest",
        sa.Column("profile_version", sa.String(32), nullable=False, server_default=""),
    )
    op.add_column(
        "context_manifest",
        sa.Column("prompt_version", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "context_manifest",
        sa.Column("rendered_hash", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "context_manifest", sa.Column("tokens", JSONB, nullable=False, server_default="{}")
    )
    op.add_column(
        "context_manifest", sa.Column("dropped", JSONB, nullable=False, server_default="[]")
    )


def downgrade() -> None:
    op.drop_column("context_manifest", "dropped")
    op.drop_column("context_manifest", "tokens")
    op.drop_column("context_manifest", "rendered_hash")
    op.drop_column("context_manifest", "prompt_version")
    op.drop_column("context_manifest", "profile_version")
    op.drop_column("context_manifest", "profile_name")
    op.drop_column("context_manifest", "role")
    op.drop_column("model_call", "actor_id")
    op.drop_column("model_call", "prompt_hash")
    op.drop_column("model_call", "task_run_id")
    op.drop_column("model_call", "phase_run_id")
    op.drop_column("model_call", "role")
