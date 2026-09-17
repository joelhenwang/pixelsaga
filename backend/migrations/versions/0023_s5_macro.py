"""Stage 5 macro simulation and genealogy tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0023_s5_macro"
down_revision = "0022_s3_hook_phase"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "macro_period_run",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id", PG_UUID(as_uuid=True), sa.ForeignKey("world.id"), nullable=False, index=True
        ),
        sa.Column("start_absolute", sa.Integer, nullable=False),
        sa.Column("end_absolute", sa.Integer, nullable=False),
        sa.Column("resolution", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="planned"),
        sa.Column("seed", sa.BigInteger, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("end_absolute > start_absolute", name="ck_macro_run_range"),
        sa.CheckConstraint("version >= 0", name="ck_macro_run_version"),
        sa.UniqueConstraint(
            "world_id", "start_absolute", "end_absolute", "resolution", name="uq_macro_run_period"
        ),
    )
    op.create_table(
        "macro_aggregate_effect",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("macro_period_run.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "world_id", PG_UUID(as_uuid=True), sa.ForeignKey("world.id"), nullable=False, index=True
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("target_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("detail", sa.String(2000), nullable=False),
        sa.Column("event_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_table(
        "macro_interruption",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("macro_period_run.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "world_id", PG_UUID(as_uuid=True), sa.ForeignKey("world.id"), nullable=False, index=True
        ),
        sa.Column("at_absolute", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(16), nullable=False),
        sa.Column("detail", sa.String(2000), nullable=False),
    )
    op.create_table(
        "lineage_link",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id", PG_UUID(as_uuid=True), sa.ForeignKey("world.id"), nullable=False, index=True
        ),
        sa.Column(
            "parent_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "child_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("birth_absolute", sa.Integer, nullable=False),
        sa.CheckConstraint("parent_id != child_id", name="ck_lineage_distinct"),
        sa.UniqueConstraint("world_id", "parent_id", "child_id", name="uq_lineage_link"),
    )
    op.create_table(
        "lineage_character",
        sa.Column(
            "character_id", PG_UUID(as_uuid=True), sa.ForeignKey("character.id"), primary_key=True
        ),
        sa.Column(
            "world_id", PG_UUID(as_uuid=True), sa.ForeignKey("world.id"), nullable=False, index=True
        ),
        sa.Column("birth_absolute", sa.Integer, nullable=False),
        sa.Column("death_absolute", sa.Integer, nullable=True),
        sa.Column("life_status", sa.String(16), nullable=False, server_default="alive"),
        sa.Column("succession_eligible", sa.Boolean, nullable=False, server_default="false"),
        sa.CheckConstraint(
            "death_absolute IS NULL OR death_absolute >= birth_absolute",
            name="ck_lineage_char_death",
        ),
    )
    op.create_table(
        "focus_assignment",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id", PG_UUID(as_uuid=True), sa.ForeignKey("world.id"), nullable=False, index=True
        ),
        sa.Column("slot", sa.String(16), nullable=False),
        sa.Column(
            "from_character_id", PG_UUID(as_uuid=True), sa.ForeignKey("character.id"), nullable=True
        ),
        sa.Column(
            "to_character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("effective_absolute", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_focus_version"),
    )
    op.create_table(
        "era_summary",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id", PG_UUID(as_uuid=True), sa.ForeignKey("world.id"), nullable=False, index=True
        ),
        sa.Column(
            "owner_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("start_absolute", sa.Integer, nullable=False),
        sa.Column("end_absolute", sa.Integer, nullable=False),
        sa.Column("text", sa.String(8000), nullable=False),
        sa.Column("source_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("profile_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("prompt_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("fallback", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.CheckConstraint("end_absolute > start_absolute", name="ck_era_range"),
        sa.CheckConstraint("version >= 1", name="ck_era_version"),
    )
    op.create_table(
        "end_condition_evidence",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id", PG_UUID(as_uuid=True), sa.ForeignKey("world.id"), nullable=False, index=True
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("evaluated_absolute", sa.Integer, nullable=False),
        sa.Column("window_start_absolute", sa.Integer, nullable=False),
        sa.Column("satisfied", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("evidence_event_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("detail", sa.String(2000), nullable=False),
        sa.CheckConstraint(
            "window_start_absolute <= evaluated_absolute",
            name="ck_end_window",
        ),
    )


def downgrade() -> None:
    for table in (
        "end_condition_evidence",
        "era_summary",
        "focus_assignment",
        "lineage_character",
        "lineage_link",
        "macro_interruption",
        "macro_aggregate_effect",
        "macro_period_run",
    ):
        op.drop_table(table)
