"""Async engine and session factory (owned by S0-DB-001)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from worldsim.infrastructure.settings import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Create the application async engine from validated settings."""
    return create_async_engine(
        settings.database.url,
        pool_size=settings.database.pool_size,
        pool_pre_ping=True,
        echo=False,
    )


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Request-scoped sessions; callers own commit/rollback per unit of work."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def check_connectivity(engine: AsyncEngine) -> str:
    """Open, use, and release one connection; return the server version."""
    async with engine.connect() as connection:
        version = (await connection.execute(text("SHOW server_version"))).scalar_one()
        assert isinstance(version, str)
        return version
