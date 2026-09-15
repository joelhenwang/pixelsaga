"""Dependency readiness without credentials (owned by S0-OPS-001).

Read-only introspection: process identity comes from settings and package
metadata, database facts from fixed introspection SQL. Failure details
carry exception type names only, never messages, because messages can
embed connection strings. Routes map the report to HTTP DTOs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

import worldsim
from worldsim.domain.schema import SCHEMA_VERSION
from worldsim.infrastructure.settings import Settings


@dataclass(frozen=True)
class DependencyCheckResult:
    name: str
    status: Literal["ok", "degraded", "failed"]
    detail: str = ""


@dataclass(frozen=True)
class ReadinessReport:
    status: Literal["ready", "degraded"]
    version: str
    environment: str
    migration_head: str | None
    schema_version: int
    checks: tuple[DependencyCheckResult, ...]


def _script_heads(migrations_dir: Path) -> list[str]:
    config = Config()
    config.set_main_option("script_location", str(migrations_dir))
    return list(ScriptDirectory.from_config(config).get_heads())


async def check_readiness(
    engine: AsyncEngine, settings: Settings, migrations_dir: Path
) -> ReadinessReport:
    checks: list[DependencyCheckResult] = []
    migration_head: str | None = None
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        checks.append(DependencyCheckResult(name="database", status="ok"))
    except Exception as exc:
        checks.append(
            DependencyCheckResult(
                name="database", status="failed", detail=f"unreachable:{type(exc).__name__}"
            )
        )
        return _report(settings, migration_head, checks)

    try:
        async with engine.connect() as connection:
            applied = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one_or_none()
            migration_head = str(applied) if applied is not None else None
            extension = (
                await connection.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                )
            ).scalar_one_or_none()
            worlds = (await connection.execute(text("SELECT COUNT(*) FROM world"))).scalar_one()
            seeds = [
                row[0]
                for row in (
                    await connection.execute(text("SELECT DISTINCT seed_version FROM world"))
                ).all()
            ]
    except Exception as exc:
        checks.append(
            DependencyCheckResult(
                name="migrations", status="failed", detail=f"unreadable:{type(exc).__name__}"
            )
        )
        return _report(settings, migration_head, checks)

    try:
        heads = _script_heads(migrations_dir)
    except Exception as exc:
        checks.append(
            DependencyCheckResult(
                name="migrations", status="failed", detail=f"history:{type(exc).__name__}"
            )
        )
        return _report(settings, migration_head, checks)
    if len(heads) != 1:
        checks.append(
            DependencyCheckResult(name="migrations", status="failed", detail=f"heads:{len(heads)}")
        )
    elif migration_head != heads[0]:
        checks.append(
            DependencyCheckResult(
                name="migrations",
                status="failed",
                detail=f"behind:{migration_head}",
            )
        )
    else:
        checks.append(DependencyCheckResult(name="migrations", status="ok", detail=heads[0]))
    checks.append(
        DependencyCheckResult(
            name="extensions",
            status="ok" if extension is not None else "failed",
            detail="vector" if extension is not None else "vector:missing",
        )
    )
    checks.append(
        DependencyCheckResult(
            name="seed",
            status="ok" if worlds > 0 else "degraded",
            detail=f"worlds:{worlds} versions:{','.join(sorted(seeds))}",
        )
    )
    checks.append(
        DependencyCheckResult(
            name="model_profile",
            status="ok",
            detail=f"active:{settings.provider.active_profile}",
        )
    )
    return _report(settings, migration_head, checks)


def _report(
    settings: Settings, migration_head: str | None, checks: list[DependencyCheckResult]
) -> ReadinessReport:
    failed = any(check.status == "failed" for check in checks)
    degraded = failed or any(check.status == "degraded" for check in checks)
    return ReadinessReport(
        status="degraded" if degraded else "ready",
        version=worldsim.__version__,
        environment=settings.app.environment,
        migration_head=migration_head,
        schema_version=SCHEMA_VERSION,
        checks=tuple(checks),
    )
