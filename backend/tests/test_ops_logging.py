"""S0-OPS-001: redacted structured logs and clean diagnostics (owned by S0-OPS-001)."""

from __future__ import annotations

import io
import json
import logging

import pytest

from worldsim.application.correlation import request_id_var
from worldsim.infrastructure.ops.logging import RedactingJsonFormatter, install, secret_values
from worldsim.infrastructure.settings import Settings, dependency_report

SENTINELS = ("sentinel-api-key-999", "sentinel-db-pw-999", "sentinel-or-key-999")


@pytest.fixture
def secrets_env(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("WORLDSIM_SECURITY__API_KEY", SENTINELS[0])
    monkeypatch.setenv(
        "WORLDSIM_DATABASE__URL",
        f"postgresql+asyncpg://worldsim:{SENTINELS[1]}@localhost:5432/worldsim",
    )
    monkeypatch.setenv("WORLDSIM_PROVIDER__OPENROUTER_API_KEY", SENTINELS[2])
    return Settings()


def _capture(settings: Settings) -> tuple[logging.Logger, io.StringIO]:
    logger = install(settings)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingJsonFormatter(secret_values(settings)))
    logger.addHandler(handler)
    return logger, stream


def _records(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_log_output_redacts_values_and_shapes(secrets_env: Settings) -> None:
    logger, stream = _capture(secrets_env)
    token = request_id_var.set("req-log-test-1")
    try:
        logger.info("key=%s bearer=%s", SENTINELS[0], f"Bearer {SENTINELS[2]}")
        logger.info("url is %s", secrets_env.database.url)
    finally:
        request_id_var.reset(token)
    output = stream.getvalue()
    for sentinel in SENTINELS:
        assert sentinel not in output
    assert "[REDACTED" in output
    records = _records(stream)
    assert all(record["request_id"] == "req-log-test-1" for record in records)
    assert all(
        set(record) >= {"ts", "level", "logger", "message", "request_id"} for record in records
    )


def test_log_exception_redacts_dsn(secrets_env: Settings) -> None:
    logger, stream = _capture(secrets_env)
    try:
        raise ValueError(f"connect failed: postgresql://u:{SENTINELS[1]}@h/db")
    except ValueError:
        logger.exception("database went away")
    output = stream.getvalue()
    assert SENTINELS[1] not in output
    assert "[REDACTED" in output


def test_diagnostics_carry_no_secrets(secrets_env: Settings) -> None:
    report = dependency_report(secrets_env)
    dumped = json.dumps(report)
    assert secret_values(secrets_env), "sentinels must be detected as secrets"
    for value in secret_values(secrets_env):
        assert value not in dumped
