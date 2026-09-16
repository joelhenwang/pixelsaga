"""LangGraph checkpoint schema (separate namespace, operational only)."""

from __future__ import annotations

from alembic import op

revision = "0005_graph_checkpoints"
down_revision = "0004_stage1_scenes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS graph_state")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS graph_state CASCADE")
