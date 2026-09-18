"""Application shell foundations: story catalog, setup snapshots, drafts, presets."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0030_application_shell"
down_revision = "0029_revamp_conditions"
branch_labels = None
depends_on = None

WORLD_PRESET_ID = "20000000-0000-4000-8000-000000000001"
WREN_PRESET_ID = "20000000-0000-4000-8000-000000000101"
ASH_PRESET_ID = "20000000-0000-4000-8000-000000000102"
STYLE_PRESET_ID = "20000000-0000-4000-8000-000000000201"
TEMPLATE_PRESET_ID = "20000000-0000-4000-8000-000000000301"


def upgrade() -> None:
    op.create_table(
        "story_catalog",
        sa.Column("world_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("cover_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_played_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_version", sa.Integer(), nullable=False),
        sa.CheckConstraint("metadata_version >= 1", name="ck_catalog_metadata_version"),
        sa.ForeignKeyConstraint(["world_id"], ["world.id"], name="fk_catalog_world"),
        sa.PrimaryKeyConstraint("world_id"),
    )
    op.create_table(
        "story_initial_setup",
        sa.Column("world_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provenance", sa.String(length=32), nullable=False),
        sa.CheckConstraint("schema_version >= 1", name="ck_setup_schema_version"),
        sa.ForeignKeyConstraint(["world_id"], ["world.id"], name="fk_setup_world"),
        sa.PrimaryKeyConstraint("world_id"),
    )
    op.create_table(
        "story_draft",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_step", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_world_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("version >= 1", name="ck_draft_version"),
        sa.ForeignKeyConstraint(["created_world_id"], ["world.id"], name="fk_draft_created_world"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_draft_created_world", "story_draft", ["created_world_id"])
    op.create_table(
        "preset",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("builtin", sa.Boolean(), nullable=False),
        sa.Column("readonly", sa.Boolean(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("current_revision >= 1", name="ck_preset_revision"),
        sa.CheckConstraint("version >= 0", name="ck_preset_version"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_preset_kind", "preset", ["kind"])
    op.create_table(
        "preset_revision",
        sa.Column("preset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_revision_number"),
        sa.ForeignKeyConstraint(["preset_id"], ["preset.id"], name="fk_revision_preset"),
        sa.PrimaryKeyConstraint("preset_id", "revision"),
    )
    op.create_table(
        "story_creation_receipt",
        sa.Column("operator", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=128), nullable=False),
        sa.Column("created_world_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_world_id"], ["world.id"], name="fk_receipt_world"),
        sa.PrimaryKeyConstraint("operator", "idempotency_key"),
    )
    op.create_index("ix_receipt_world", "story_creation_receipt", ["created_world_id"])

    # Backfill: one catalog entry plus an honest legacy-unknown setup per world.
    op.execute(
        sa.text(
            "INSERT INTO story_catalog "
            "(world_id, title, cover_asset_id, created_at, last_played_at, "
            "archived_at, metadata_version) "
            "SELECT id, name, NULL, now(), NULL, NULL, 1 FROM world"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO story_initial_setup "
            "(world_id, schema_version, payload, content_hash, created_at, provenance) "
            "SELECT id, 1, "
            '\'{"schema_version": 1, "provenance": "legacy_unknown"}\', '
            "'legacy-unknown', now(), 'legacy_unknown' FROM world"
        )
    )
    for preset_id, kind, name, payload in _builtin_presets():
        op.execute(
            sa.text(
                "INSERT INTO preset (id, kind, name, builtin, readonly, archived_at, "
                "current_revision, version, created_at) VALUES "
                "(:id, :kind, :name, TRUE, TRUE, NULL, 1, 0, now())"
            ).bindparams(
                sa.bindparam(
                    "id",
                    type_=postgresql.UUID(as_uuid=True),
                    value=uuid.UUID(preset_id),
                ),
                kind=kind,
                name=name,
            )
        )
        op.execute(
            sa.text(
                "INSERT INTO preset_revision (preset_id, revision, schema_version, "
                "payload, content_hash, created_at) VALUES "
                "(:id, 1, 1, CAST(:payload AS JSONB), 'builtin-v1', now())"
            ).bindparams(
                sa.bindparam(
                    "id",
                    type_=postgresql.UUID(as_uuid=True),
                    value=uuid.UUID(preset_id),
                ),
                payload=payload,
            )
        )


def downgrade() -> None:
    op.drop_index("ix_receipt_world", table_name="story_creation_receipt")
    op.drop_table("story_creation_receipt")
    op.drop_table("preset_revision")
    op.drop_index("ix_preset_kind", table_name="preset")
    op.drop_table("preset")
    op.drop_index("ix_draft_created_world", table_name="story_draft")
    op.drop_table("story_draft")
    op.drop_table("story_initial_setup")
    op.drop_table("story_catalog")


def _builtin_presets() -> list[tuple[str, str, str, str]]:
    world_payload = (
        '{"kind": "world", "name": "Ember Vale", '
        '"description": "A sheltered vale of hearths, markets, and old roads.", '
        '"lore": "The vale keeps its stories close.", '
        '"locations": [{"key": "hearth", "name": "Hearth"}, '
        '{"key": "market", "name": "Market"}], "travel": [], '
        '"starting_location_key": "hearth", "default_cast": ["wren", "ash"], '
        '"style_pack_id": "anime-saga-v1"}'
    )
    wren_payload = (
        '{"kind": "character", "name": "Wren", '
        '"appearance": "Quick eyes and a traveler\'s coat.", '
        '"personality": "Curious, kind, asks what if.", '
        '"background": "Road-raised and story-fed.", '
        '"portrait_asset_id": null, "tags": ["Human", "Explorer", "Player-ready"], '
        '"starting_location_key": "hearth"}'
    )
    ash_payload = (
        '{"kind": "character", "name": "Ash", '
        '"appearance": "Steady stance, weather-worn cloak.", '
        '"personality": "Patient, dry-witted, dependable.", '
        '"background": "Market ward born and bred.", '
        '"portrait_asset_id": null, "tags": ["Human", "Wanderer", "Player-ready"], '
        '"starting_location_key": "market"}'
    )
    style_payload = (
        '{"kind": "style_pack", "display_name": "Anime Saga", '
        '"style_id": "anime-saga-v1", '
        '"guidance": "Warm anime-fantasy key art with expressive portraits."}'
    )
    template_payload = (
        '{"kind": "template", "display_name": "Ember Vale opening", '
        f'"world_preset_id": "{WORLD_PRESET_ID}", "world_preset_revision": 1, '
        f'"cast_preset_ids": ["{WREN_PRESET_ID}", "{ASH_PRESET_ID}"], '
        '"tone": "hopeful mystery", "pacing": "measured"}'
    )
    return [
        (WORLD_PRESET_ID, "world", "Ember Vale", world_payload),
        (WREN_PRESET_ID, "character", "Wren", wren_payload),
        (ASH_PRESET_ID, "character", "Ash", ash_payload),
        (STYLE_PRESET_ID, "style_pack", "Anime Saga", style_payload),
        (TEMPLATE_PRESET_ID, "template", "Ember Vale opening", template_payload),
    ]
