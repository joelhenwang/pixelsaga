"""Database URL conversions (owned by S0-DB-001)."""

from __future__ import annotations

ASYNC_PREFIX = "postgresql+asyncpg://"
SYNC_PREFIX = "postgresql://"


def to_sync_url(async_url: str) -> str:
    """Convert the async SQLAlchemy URL into a sync psycopg DSN."""
    if async_url.startswith(ASYNC_PREFIX):
        return SYNC_PREFIX + async_url[len(ASYNC_PREFIX) :]
    return async_url
