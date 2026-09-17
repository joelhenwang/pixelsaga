"""Stage 5 world-ended event type."""

from __future__ import annotations

from alembic import op

revision = "0025_s5_world_ended"
down_revision = "0024_s5_macro_event_type"
branch_labels = None
depends_on = None

_EVENT_TYPES = (
    "'world_seeded','world_ticked','macro_ticked','action_resolved',"
    "'schedule_fired','deity_override','world_ended'"
)
_EVENT_TYPES_DOWN = (
    "'world_seeded','world_ticked','macro_ticked','action_resolved',"
    "'schedule_fired','deity_override'"
)


def upgrade() -> None:
    op.drop_constraint("ck_event_type", "world_event", type_="check")
    op.create_check_constraint("ck_event_type", "world_event", f"event_type IN ({_EVENT_TYPES})")


def downgrade() -> None:
    op.drop_constraint("ck_event_type", "world_event", type_="check")
    op.create_check_constraint(
        "ck_event_type", "world_event", f"event_type IN ({_EVENT_TYPES_DOWN})"
    )
