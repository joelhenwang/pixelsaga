"""Stage 3 model-call cost records."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0021_s3_costs"
down_revision = "0020_s3_digests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_cost",
        sa.Column("call_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_cost_world"),
            nullable=True,
            index=True,
        ),
        sa.Column("pricing_version", sa.String(32), nullable=False),
        sa.Column("model", sa.String(256), nullable=False, server_default=""),
        sa.Column("prompt_tokens", sa.Integer, nullable=False),
        sa.Column("completion_tokens", sa.Integer, nullable=False),
        sa.Column("prompt_cost_usd", sa.Float, nullable=False),
        sa.Column("completion_cost_usd", sa.Float, nullable=False),
        sa.Column("estimated", sa.Boolean, nullable=False, server_default="false"),
        sa.CheckConstraint("prompt_tokens >= 0", name="ck_cost_prompt_tokens"),
        sa.CheckConstraint("completion_tokens >= 0", name="ck_cost_completion_tokens"),
        sa.CheckConstraint("prompt_cost_usd >= 0", name="ck_cost_prompt_usd"),
        sa.CheckConstraint("completion_cost_usd >= 0", name="ck_cost_completion_usd"),
    )


def downgrade() -> None:
    op.drop_table("model_cost")
