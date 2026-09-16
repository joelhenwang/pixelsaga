"""Resolution seed widens to 64-bit (deterministic UUID-derived evidence)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_resolution_seed_bigint"
down_revision = "0006_narration_cited_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("resolution", "random_seed", type_=sa.BigInteger(), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("resolution", "random_seed", type_=sa.Integer(), existing_nullable=False)
