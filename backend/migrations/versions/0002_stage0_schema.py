"""Stage 0 schema: only tables the Stage 0 scenario reads and writes.

Snapshots are immutable via trigger; no Stage 1 tables; no vector columns.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0002_stage0_schema"
down_revision = "0001_enable_pgvector"
branch_labels = None
depends_on = None

_PHASE_RUN_STATES = (
    "'created','world_ticked','snapshot_sealed','director_complete',"
    "'intents_complete','scenes_assembled','scenes_committed',"
    "'perception_complete','post_commit_queued','completed','paused',"
    "'retryable_failed','terminal_failed','cancelled'"
)
_TASK_STATES = "'pending','claimed','running','succeeded','retry_wait','dead_letter','cancelled'"
_PHASES = (
    "'dawn','sunrise','morning','noon','afternoon','sunset','dusk','evening','night','midnight'"
)


def _stamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "world",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("seed_version", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        *_stamps(),
        sa.CheckConstraint("status IN ('active', 'paused', 'ended')", name="ck_world_status"),
        sa.CheckConstraint("version >= 0", name="ck_world_version"),
    )
    op.create_table(
        "world_config",
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_world_config_world"),
            primary_key=True,
        ),
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", JSONB, nullable=False),
    )
    op.create_table(
        "world_clock",
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_world_clock_world"),
            primary_key=True,
        ),
        sa.Column("day", sa.Integer, nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("absolute_index", sa.Integer, nullable=False),
        sa.CheckConstraint("day >= 1", name="ck_world_clock_day"),
        sa.CheckConstraint(f"phase IN ({_PHASES})", name="ck_world_clock_phase"),
        sa.CheckConstraint("absolute_index >= 0", name="ck_world_clock_index"),
    )
    op.create_table(
        "entity",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_entity_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("created_phase_index", sa.Integer, nullable=False),
        sa.CheckConstraint("kind IN ('character','location')", name="ck_entity_kind"),
        sa.CheckConstraint("created_phase_index >= 0", name="ck_entity_phase"),
    )
    op.create_table(
        "location",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("entity.id", name="fk_location_entity"),
            primary_key=True,
        ),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_location_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("region", sa.String(128), nullable=False, server_default=""),
        sa.Column("capacity", sa.Integer, nullable=True),
        sa.Column("routes", JSONB, nullable=False),
        sa.Column("discovered", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("capacity IS NULL OR capacity >= 1", name="ck_location_capacity"),
        sa.CheckConstraint("version >= 0", name="ck_location_version"),
        sa.UniqueConstraint("world_id", "name", name="uq_location_world_name"),
    )
    op.create_table(
        "character",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("entity.id", name="fk_character_entity"),
            primary_key=True,
        ),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_character_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(128), nullable=False),
    )
    op.create_table(
        "character_card_version",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_card_character"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("appearance", sa.String(2000), nullable=False, server_default=""),
        sa.Column("personality", sa.String(2000), nullable=False, server_default=""),
        sa.Column("background", sa.String(2000), nullable=False, server_default=""),
        sa.CheckConstraint("version >= 1", name="ck_card_version"),
        sa.UniqueConstraint("character_id", "version", name="uq_card_character_version"),
    )
    op.create_table(
        "character_state",
        sa.Column(
            "character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_state_character"),
            primary_key=True,
        ),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_state_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("card_version", sa.Integer, nullable=False),
        sa.Column("life_status", sa.String(16), nullable=False, server_default="alive"),
        sa.Column(
            "location_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("location.id", name="fk_state_location"),
            nullable=False,
            index=True,
        ),
        sa.Column("stamina", sa.Integer, nullable=False),
        sa.Column("mana", sa.Integer, nullable=False),
        sa.Column("conditions", JSONB, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("card_version >= 1", name="ck_state_card_version"),
        sa.CheckConstraint("life_status IN ('alive','dead')", name="ck_state_life"),
        sa.CheckConstraint("stamina BETWEEN 0 AND 100", name="ck_state_stamina"),
        sa.CheckConstraint("mana BETWEEN 0 AND 100", name="ck_state_mana"),
        sa.CheckConstraint("version >= 0", name="ck_state_version"),
    )
    op.create_table(
        "phase_run",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_phase_run_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("absolute_index", sa.Integer, nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="created"),
        *_stamps(),
        sa.CheckConstraint("absolute_index >= 0", name="ck_phase_run_index"),
        sa.CheckConstraint(f"state IN ({_PHASE_RUN_STATES})", name="ck_phase_run_state"),
        sa.UniqueConstraint("world_id", "absolute_index", name="uq_phase_run_world_index"),
    )
    op.create_table(
        "phase_snapshot",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_snapshot_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "phase_run_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("phase_run.id", name="fk_snapshot_run"),
            nullable=False,
            unique=True,
        ),
        sa.Column("absolute_index", sa.Integer, nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("world_version", sa.Integer, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("absolute_index >= 0", name="ck_snapshot_index"),
        sa.CheckConstraint("schema_version >= 1", name="ck_snapshot_schema"),
        sa.CheckConstraint("world_version >= 0", name="ck_snapshot_world_version"),
    )
    op.create_table(
        "phase_snapshot_character",
        sa.Column(
            "snapshot_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("phase_snapshot.id", name="fk_snapchar_snapshot"),
            primary_key=True,
        ),
        sa.Column(
            "character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_snapchar_character"),
            primary_key=True,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.CheckConstraint("version >= 0", name="ck_snapchar_version"),
    )
    op.create_table(
        "user_command",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_command_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor_role", sa.String(16), nullable=False),
        sa.Column("command_type", sa.String(32), nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("expected_versions", JSONB, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("result_event_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actor_role IN ('watcher','director','deity','player','system')",
            name="ck_command_actor",
        ),
        sa.CheckConstraint("schema_version >= 1", name="ck_command_schema"),
        sa.UniqueConstraint("world_id", "idempotency_key", name="uq_command_world_key"),
    )
    op.create_table(
        "task_run",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_task_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("owner", sa.String(128), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("input_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        *_stamps(),
        sa.UniqueConstraint("world_id", "idempotency_key", name="uq_task_world_key"),
    )
    op.create_table(
        "world_event",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_event_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("absolute_index", sa.Integer, nullable=False),
        sa.Column(
            "phase_run_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("phase_run.id", name="fk_event_run"),
            nullable=True,
        ),
        sa.Column(
            "source_command_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("user_command.id", name="fk_event_command"),
            nullable=True,
        ),
        sa.Column(
            "source_task_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("task_run.id", name="fk_event_task"),
            nullable=True,
        ),
        sa.Column("participant_ids", JSONB, nullable=False),
        sa.Column("summary", JSONB, nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="public"),
        sa.Column("random_seed", sa.Integer, nullable=True),
        sa.Column("random_algorithm", sa.String(64), nullable=True),
        sa.Column("random_result", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_event_sequence"),
        sa.CheckConstraint(
            "event_type IN ('world_seeded','world_ticked','action_resolved')",
            name="ck_event_type",
        ),
        sa.CheckConstraint("schema_version >= 1", name="ck_event_schema"),
        sa.CheckConstraint("absolute_index >= 0", name="ck_event_index"),
        sa.CheckConstraint("visibility IN ('public','private')", name="ck_event_visibility"),
        sa.UniqueConstraint("world_id", "sequence", name="uq_event_world_sequence"),
    )
    op.create_foreign_key(
        "fk_command_result",
        "user_command",
        "world_event",
        ["result_event_id"],
        ["id"],
    )
    op.create_table(
        "event_effect",
        sa.Column(
            "event_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world_event.id", name="fk_effect_event"),
            primary_key=True,
        ),
        sa.Column("ordinal", sa.Integer, primary_key=True),
        sa.Column("effect_type", sa.String(32), nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("payload", JSONB, nullable=False),
        sa.CheckConstraint("ordinal >= 0", name="ck_effect_ordinal"),
        sa.CheckConstraint(
            "effect_type IN ('advance_clock','move_entity','resource_adjusted',"
            "'record_observation','record_memory')",
            name="ck_effect_type",
        ),
        sa.CheckConstraint("schema_version >= 1", name="ck_effect_schema"),
    )
    op.create_table(
        "observation",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_obs_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "event_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world_event.id", name="fk_obs_event"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "observer_character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_obs_observer"),
            nullable=False,
            index=True,
        ),
        sa.Column("facts", JSONB, nullable=False),
        sa.Column("created_phase_index", sa.Integer, nullable=False),
        sa.CheckConstraint("created_phase_index >= 0", name="ck_obs_phase"),
    )
    op.create_table(
        "recent_memory",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_mem_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "owner_character_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("character.id", name="fk_mem_owner"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "event_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world_event.id", name="fk_mem_event"),
            nullable=True,
        ),
        sa.Column(
            "observation_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("observation.id", name="fk_mem_obs"),
            nullable=True,
        ),
        sa.Column("text", sa.String(2000), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="private"),
        sa.Column("created_phase_index", sa.Integer, nullable=False),
        sa.CheckConstraint("visibility IN ('public','private')", name="ck_mem_visibility"),
        sa.CheckConstraint("created_phase_index >= 0", name="ck_mem_phase"),
    )
    op.create_table(
        "aggregate_version",
        sa.Column("aggregate_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_aggver_world"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_aggver_version"),
    )
    op.create_table(
        "outbox_message",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_outbox_world"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "event_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world_event.id", name="fk_outbox_event"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('pending','claimed','acked','failed')", name="ck_outbox_state"
        ),
        sa.UniqueConstraint("world_id", "idempotency_key", name="uq_outbox_world_key"),
    )
    op.create_table(
        "model_profile",
        sa.Column("name", sa.String(64), primary_key=True),
        sa.Column("version", sa.String(32), primary_key=True),
        sa.Column("adapter", sa.String(16), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("max_context_tokens", sa.Integer, nullable=False),
        sa.Column("capabilities", JSONB, nullable=False),
        sa.CheckConstraint("adapter IN ('fake','openrouter')", name="ck_profile_adapter"),
        sa.CheckConstraint("max_context_tokens >= 1", name="ck_profile_context"),
    )
    op.create_table(
        "model_call",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_call_world"),
            nullable=True,
        ),
        sa.Column("profile_name", sa.String(64), nullable=False),
        sa.Column("profile_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="started"),
        sa.Column("request", JSONB, nullable=False),
        sa.Column("result", JSONB, nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_name", "profile_version"],
            ["model_profile.name", "model_profile.version"],
            name="fk_call_profile",
        ),
        sa.CheckConstraint("status IN ('started','succeeded','failed')", name="ck_call_status"),
        sa.CheckConstraint("prompt_tokens >= 0", name="ck_call_prompt_tokens"),
        sa.CheckConstraint("completion_tokens >= 0", name="ck_call_completion_tokens"),
        sa.CheckConstraint("latency_ms >= 0", name="ck_call_latency"),
    )
    op.create_table(
        "context_manifest",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("model_call.id", name="fk_manifest_call"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "world_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_manifest_world"),
            nullable=True,
        ),
        sa.Column("sources", JSONB, nullable=False),
        sa.Column("budgets", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION forbid_snapshot_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'phase_snapshot is immutable'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER phase_snapshot_no_mutation BEFORE UPDATE OR DELETE ON phase_snapshot "
        "FOR EACH ROW EXECUTE FUNCTION forbid_snapshot_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS phase_snapshot_no_mutation ON phase_snapshot")
    op.execute("DROP FUNCTION IF EXISTS forbid_snapshot_mutation()")
    op.drop_constraint("fk_command_result", "user_command", type_="foreignkey")
    for table in (
        "context_manifest",
        "model_call",
        "model_profile",
        "outbox_message",
        "aggregate_version",
        "recent_memory",
        "observation",
        "event_effect",
        "world_event",
        "task_run",
        "user_command",
        "phase_snapshot_character",
        "phase_snapshot",
        "phase_run",
        "character_state",
        "character_card_version",
        "character",
        "location",
        "entity",
        "world_clock",
        "world_config",
        "world",
    ):
        op.drop_table(table)
