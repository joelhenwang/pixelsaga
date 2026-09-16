"""Narration cited-fact keys (audit for the unsupported-fact validator)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_narration_cited_keys"
down_revision = "0005_graph_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "narration",
        sa.Column("cited_fact_keys", JSONB, server_default=sa.text("'[]'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("narration", "cited_fact_keys")
