"""Stage 5 macro tick event type."""

from __future__ import annotations

from alembic import op

revision = "0024_s5_macro_event_type"
down_revision = "0023_s5_macro"
branch_labels = None
depends_on = None

_EVENT_TYPES = (
    "'world_seeded','world_ticked','macro_ticked','action_resolved',"
    "'schedule_fired','deity_override'"
)
_EVENT_TYPES_DOWN = (
    "'world_seeded','world_ticked','action_resolved','schedule_fired','deity_override'"
)


def upgrade() -> None:
    op.drop_constraint("ck_event_type", "world_event", type_="check")
    op.create_check_constraint("ck_event_type", "world_event", f"event_type IN ({_EVENT_TYPES})")


def downgrade() -> None:
    op.drop_constraint("ck_event_type", "world_event", type_="check")
    op.create_check_constraint(
        "ck_event_type", "world_event", f"event_type IN ({_EVENT_TYPES_DOWN})"
    )
