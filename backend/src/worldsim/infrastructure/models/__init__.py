"""SQLAlchemy declarative base (owned by S0-DB-001).

No tables live here yet; S0-DB-002 owns the Stage 0 mappings. The
deterministic naming convention keeps constraint names stable across
autogenerate cycles.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


from worldsim.infrastructure.models import (  # noqa: E402
    calls,
    characters,
    commands,
    events,
    macro,
    perception,
    phases,
    scenes,
    tasks,
    versions,
    world,
)

__all__ = [
    "calls",
    "characters",
    "commands",
    "events",
    "macro",
    "perception",
    "phases",
    "scenes",
    "tasks",
    "versions",
    "world",
]
