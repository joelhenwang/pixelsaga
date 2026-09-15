"""Migration status and verification (owned by S0-DB-001)."""

from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.engine import Connection as SyncConnection
from sqlalchemy.ext.asyncio import AsyncEngine


def _has_version_table(sync_conn: SyncConnection) -> bool:
    return sync_conn.dialect.has_table(sync_conn, "alembic_version")


class MigrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current: str | None
    heads: list[str]
    multiple_heads: bool
    up_to_date: bool


def script_heads(config: Config) -> list[str]:
    return list(ScriptDirectory.from_config(config).get_heads())


def detect_multiple_heads(script: ScriptDirectory) -> list[str]:
    """Return every head; more than one means divergent history."""
    return list(script.get_heads())


async def database_current(engine: AsyncEngine) -> str | None:
    """Read the alembic version table; None means no migration has run."""
    async with engine.connect() as connection:
        if not await connection.run_sync(_has_version_table):
            return None
        revision = (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one_or_none()
        assert revision is None or isinstance(revision, str)
        return revision


async def verify(engine: AsyncEngine, config: Config) -> MigrationReport:
    heads = script_heads(config)
    current = await database_current(engine)
    return MigrationReport(
        current=current,
        heads=heads,
        multiple_heads=len(heads) > 1,
        up_to_date=current is not None and current in heads,
    )
