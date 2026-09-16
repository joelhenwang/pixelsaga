"""Event random seeds widen to 64-bit (combat roll evidence)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_event_seed_bigint"
down_revision = "0008_dnd_party"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("world_event", "random_seed", type_=sa.BigInteger(), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("world_event", "random_seed", type_=sa.Integer(), existing_nullable=True)
