"""Stage 3 salience and source hashes on perception rows."""

from __future__ import annotations

import hashlib
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0019_s3_salience"
down_revision = "0018_s2_roles"
branch_labels = None
depends_on = None


def _hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def upgrade() -> None:
    op.add_column(
        "observation",
        sa.Column("salience", sa.Float, nullable=False, server_default="1.0"),
    )
    op.add_column(
        "observation",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "recent_memory",
        sa.Column("salience", sa.Float, nullable=False, server_default="1.0"),
    )
    op.add_column(
        "recent_memory",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.create_check_constraint("ck_obs_salience", "observation", "salience >= 0 AND salience <= 5")
    op.create_check_constraint(
        "ck_mem_salience", "recent_memory", "salience >= 0 AND salience <= 5"
    )
    op.create_index("ix_mem_owner_salience", "recent_memory", ["owner_character_id", "salience"])
    op.create_index(
        "ix_obs_observer_phase", "observation", ["observer_character_id", "created_phase_index"]
    )

    connection = op.get_bind()
    for row in connection.execute(text("SELECT id, facts FROM observation")).mappings():
        facts = row["facts"] or []
        canonical = [
            {"key": fact.get("key"), "value": fact.get("value")} if isinstance(fact, dict) else fact
            for fact in facts
        ]
        connection.execute(
            text("UPDATE observation SET content_hash = :hash WHERE id = :id"),
            {"hash": _hash(canonical), "id": row["id"]},
        )
    for row in connection.execute(text("SELECT id, text FROM recent_memory")).mappings():
        connection.execute(
            text("UPDATE recent_memory SET content_hash = :hash WHERE id = :id"),
            {"hash": _hash(row["text"]), "id": row["id"]},
        )


def downgrade() -> None:
    op.drop_index("ix_obs_observer_phase", table_name="observation")
    op.drop_index("ix_mem_owner_salience", table_name="recent_memory")
    op.drop_constraint("ck_mem_salience", "recent_memory", type_="check")
    op.drop_constraint("ck_obs_salience", "observation", type_="check")
    op.drop_column("recent_memory", "content_hash")
    op.drop_column("recent_memory", "salience")
    op.drop_column("observation", "content_hash")
    op.drop_column("observation", "salience")
