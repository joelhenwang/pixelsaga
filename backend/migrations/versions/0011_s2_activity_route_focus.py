"""Stage 2 activity, route, and focus-slot contracts."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0011_s2_activity_route_focus"
down_revision = "0010_dnd_monsters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_activity_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_activity_character"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="planned"),
        sa.Column("start_absolute", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duration_phases", sa.Integer, nullable=False, server_default="1"),
        sa.Column("progress_phases", sa.Integer, nullable=False, server_default="0"),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_activity_version"),
        sa.CheckConstraint("duration_phases >= 1", name="ck_activity_duration"),
        sa.CheckConstraint("progress_phases >= 0", name="ck_activity_progress"),
    )
    op.create_table(
        "travel_route",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_route_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "from_location_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("location.id", name="fk_route_from"),
            nullable=False,
        ),
        sa.Column(
            "to_location_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("location.id", name="fk_route_to"),
            nullable=False,
        ),
        sa.Column("duration_phases", sa.Integer, nullable=False, server_default="1"),
        sa.Column("stamina_cost", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_route_version"),
        sa.CheckConstraint("duration_phases >= 1", name="ck_route_duration"),
        sa.UniqueConstraint("world_id", "from_location_id", "to_location_id", name="uq_route_legs"),
    )
    op.add_column(
        "dnd_party_member",
        sa.Column("focus_slot", sa.String(16), nullable=False, server_default="companion"),
    )
    # Seat order decides the slot: first two by name main, next two sub.
    op.execute(
        sa.text(
            "UPDATE dnd_party_member SET focus_slot = 'main' WHERE id IN ("
            "SELECT id FROM (SELECT id, ROW_NUMBER() OVER ("
            "PARTITION BY world_id ORDER BY name) AS seat FROM dnd_party_member"
            ") ranked WHERE seat <= 2)"
        )
    )
    op.execute(
        sa.text(
            "UPDATE dnd_party_member SET focus_slot = 'sub' WHERE id IN ("
            "SELECT id FROM (SELECT id, ROW_NUMBER() OVER ("
            "PARTITION BY world_id ORDER BY name) AS seat FROM dnd_party_member"
            ") ranked WHERE seat BETWEEN 3 AND 4)"
        )
    )


def downgrade() -> None:
    op.drop_column("dnd_party_member", "focus_slot")
    op.drop_table("travel_route")
    op.drop_table("activity")
