"""Stage 3 hook/arc creation phases."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_s3_hook_phase"
down_revision = "0021_s3_costs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "narrative_hook",
        sa.Column("created_phase_index", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "narrative_arc",
        sa.Column("created_phase_index", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_hook_world_phase", "narrative_hook", ["world_id", "created_phase_index"])
    op.create_index("ix_arc_world_phase", "narrative_arc", ["world_id", "created_phase_index"])


def downgrade() -> None:
    op.drop_index("ix_arc_world_phase", table_name="narrative_arc")
    op.drop_index("ix_hook_world_phase", table_name="narrative_hook")
    op.drop_column("narrative_arc", "created_phase_index")
    op.drop_column("narrative_hook", "created_phase_index")
