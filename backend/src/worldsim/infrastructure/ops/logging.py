"""JSON structured logs with secret redaction (owned by S0-OPS-001).

Every record carries the correlation request ID. Messages, arguments,
and formatted exceptions pass the trace redaction patterns plus masking
of configured secret values, so database passwords and provider keys
cannot leak through logs. ``install`` wires the ``worldsim`` logger;
libraries keep their own handlers.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import UTC, datetime

from worldsim.application.correlation import get_request_id
from worldsim.application.tracing.service import redact
from worldsim.infrastructure.settings import Settings


def secret_values(settings: Settings) -> list[str]:
    """Configured values that must never appear in output."""
    candidates = [
        settings.database.url,
        (
            settings.provider.openrouter_api_key.get_secret_value()
            if settings.provider.openrouter_api_key is not None
            else ""
        ),
        (
            settings.tracing.langsmith_api_key.get_secret_value()
            if settings.tracing.langsmith_api_key is not None
            else ""
        ),
        (
            settings.security.api_key.get_secret_value()
            if settings.security.api_key is not None
            else ""
        ),
    ]
    return sorted({value for value in candidates if value}, key=len, reverse=True)


def mask(text: str, secrets: Iterable[str]) -> str:
    redacted = redact(text)
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED:secret-value]")
    return redacted


class RedactingJsonFormatter(logging.Formatter):
    """Render records as one JSON document per line, redacted."""

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._secrets = sorted(set(secrets), key=len, reverse=True)

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        document = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": mask(message, self._secrets),
            "request_id": get_request_id(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            document["exception"] = mask(self.formatException(record.exc_info), self._secrets)
        for key, value in record.__dict__.items():
            if key not in (
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "message",
                "module",
                "msecs",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            ):
                document[f"extra_{key}"] = mask(str(value), self._secrets)
        return json.dumps(document, sort_keys=True, default=str)


def install(settings: Settings, level: str = "INFO") -> logging.Logger:
    """Attach the redacting JSON handler to the worldsim logger."""
    logger = logging.getLogger("worldsim")
    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingJsonFormatter(secret_values(settings)))
    logger.handlers = [handler]
    logger.propagate = False
    return logger
