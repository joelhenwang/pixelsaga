"""Stage 0 deterministic test harness (owned by S0-QA-001)."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fixtures.clocks import FakeOperationalClock, FictionalClock
from fixtures.fake_model_gateway import FakeModelGateway
from fixtures.faults import FaultHooks
from fixtures.postgres import sync_dsn
from fixtures.randomness import SeededRandomSource
from fixtures.scenario import StageScenario
from psycopg import Connection, connect

from worldsim.infrastructure.settings import Settings


@pytest.fixture
def operational_clock() -> FakeOperationalClock:
    return FakeOperationalClock()


@pytest.fixture
def fictional_clock() -> FictionalClock:
    return FictionalClock()


@pytest.fixture
def random_source() -> SeededRandomSource:
    return SeededRandomSource(seed=1234)


@pytest.fixture
def model_gateway() -> FakeModelGateway:
    return FakeModelGateway()


@pytest.fixture
def fault_hooks() -> FaultHooks:
    return FaultHooks()


@pytest.fixture
def stage_scenario() -> StageScenario:
    return StageScenario(name="qa-selftest")


@pytest.fixture(autouse=True)
def _block_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deny non-loopback TCP while letting localhost (PostgreSQL) through."""
    real_getaddrinfo: Any = socket.getaddrinfo
    real_connect: Any = socket.socket.connect

    def _guarded_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        if (
            isinstance(host, str)
            and host != "localhost"
            and not host.startswith("127.")
            and host != "::1"
        ):
            raise socket.gaierror("external network blocked in tests")
        return real_getaddrinfo(host, port, *args, **kwargs)

    def _guarded_connect(sock: object, address: object, *args: object) -> Any:
        host: str | None = None
        if isinstance(address, tuple):
            parts = cast("tuple[object, ...]", address)
            if len(parts) > 0 and isinstance(parts[0], str):
                host = parts[0]
        elif isinstance(address, str):
            host = address
        if host is not None:
            try:
                if not ipaddress.ip_address(host).is_loopback:
                    raise OSError(f"external network blocked in tests: {host}")
            except ValueError:
                if host != "localhost":
                    raise OSError(f"external network blocked in tests: {host}") from None
        return real_connect(sock, address, *args)

    monkeypatch.setattr(socket, "getaddrinfo", _guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)


@pytest.fixture(scope="session")
def _pg_schema() -> Iterator[None]:
    conn = connect(sync_dsn(Settings()))
    conn.autocommit = True
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS qa_rollback_probe"
            " (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
            " note text NOT NULL)"
        )
        yield
    finally:
        conn.execute("DROP TABLE IF EXISTS qa_rollback_probe")
        conn.close()


@pytest.fixture(scope="session")
def tracked_connections() -> list[Connection[Any]]:
    return []


@pytest.fixture
def pg_conn(
    _pg_schema: None, tracked_connections: list[Connection[Any]]
) -> Iterator[Connection[Any]]:
    conn = connect(sync_dsn(Settings()))
    tracked_connections.append(conn)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def migrated_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Scratch database at the migration head for application tests."""
    from fixtures.postgres import (
        create_scratch_database,
        drop_scratch_database,
        replace_database,
        upgrade_head,
    )

    from worldsim.infrastructure.settings import Settings

    name = "worldsim_stage0_test"
    settings = Settings()
    create_scratch_database(settings, name)
    monkeypatch.setenv(
        "WORLDSIM_DATABASE__URL",
        replace_database(settings.database.url, name),
    )
    upgrade_head()
    yield
    drop_scratch_database(Settings(), name)
