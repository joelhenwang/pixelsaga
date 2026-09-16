import asyncio
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import connect
from psycopg.errors import DuplicateDatabase
from sqlalchemy import text

from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.db.urls import to_sync_url
from worldsim.infrastructure.db.verify import (
    MigrationReport,
    database_current,
    detect_multiple_heads,
    script_heads,
    verify,
)
from worldsim.infrastructure.settings import Settings

SCRATCH_DB = "worldsim_migtest"
HEAD = "0014_s2_knowledge"


def _migrations_dir() -> Path:
    return Path(__file__).parent.parent / "migrations"


def _replace_database(url: str, database: str) -> str:
    parts = urlparse(url)
    return urlunparse(parts._replace(path=f"/{database}"))


@pytest.fixture
def scratch_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Create a scratch database; drop it after the test finishes."""
    base = to_sync_url(Settings().database.url)
    maintenance = _replace_database(base, "postgres")
    admin = connect(maintenance, autocommit=True)
    try:
        try:
            admin.execute(f"CREATE DATABASE {SCRATCH_DB}")
        except DuplicateDatabase:
            pass
    finally:
        admin.close()
    scratch_async = _replace_database(Settings().database.url, SCRATCH_DB)
    monkeypatch.setenv("WORLDSIM_DATABASE__URL", scratch_async)
    yield scratch_async
    admin = connect(maintenance, autocommit=True)
    try:
        admin.execute(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)")
    finally:
        admin.close()


def _config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(_migrations_dir()))
    return config


async def _current() -> str | None:
    engine = create_engine(Settings())
    try:
        return await database_current(engine)
    finally:
        await engine.dispose()


async def _extension_present() -> int:
    engine = create_engine(Settings())
    try:
        async with engine.connect() as connection:
            value = (
                await connection.execute(
                    text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
                )
            ).scalar_one()
            assert isinstance(value, int)
            return value
    finally:
        await engine.dispose()


async def _report() -> MigrationReport:
    engine = create_engine(Settings())
    try:
        return await verify(engine, _config())
    finally:
        await engine.dispose()


def test_single_head_in_history() -> None:
    assert script_heads(_config()) == [HEAD]


def test_upgrade_downgrade_reupgrade_cycle(scratch_env: str) -> None:
    config = _config()
    alembic_command.downgrade(config, "base")
    assert asyncio.run(_current()) is None
    alembic_command.upgrade(config, "head")
    assert asyncio.run(_current()) == HEAD
    assert asyncio.run(_extension_present()) == 1
    report = asyncio.run(_report())
    assert report.current == HEAD
    assert report.heads == [HEAD]
    assert not report.multiple_heads
    assert report.up_to_date
    alembic_command.downgrade(config, "base")
    assert asyncio.run(_current()) is None
    alembic_command.upgrade(config, "head")
    assert asyncio.run(_current()) == HEAD


def test_detect_multiple_heads_in_tmp_dir(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir()
    for revision in ("aaa", "bbb"):
        (versions / f"{revision}.py").write_text(
            f'revision = "{revision}"\ndown_revision = None\n\n'
            "def upgrade():\n    pass\n\ndef downgrade():\n    pass\n",
            encoding="utf-8",
        )
    config = Config()
    config.set_main_option("script_location", str(tmp_path))
    heads = detect_multiple_heads(ScriptDirectory.from_config(config))
    assert sorted(heads) == ["aaa", "bbb"]
    assert len(detect_multiple_heads(ScriptDirectory.from_config(_config()))) == 1
