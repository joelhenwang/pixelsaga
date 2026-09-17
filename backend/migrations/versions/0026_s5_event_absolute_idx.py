"""Stage 5 event absolute-position index for era scans."""

from __future__ import annotations

from alembic import op

revision = "0026_s5_event_absolute_idx"
down_revision = "0025_s5_world_ended"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_event_world_absolute", "world_event", ["world_id", "absolute_index"])


def downgrade() -> None:
    op.drop_index("ix_event_world_absolute", table_name="world_event")
