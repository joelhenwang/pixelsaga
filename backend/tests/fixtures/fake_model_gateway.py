"""Scripted fake model gateway (owned by S0-QA-001)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class ModelErrorKind(Enum):
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    MALFORMED = "malformed"
    REFUSAL = "refusal"
    UNAVAILABLE = "unavailable"


class FakeModelError(Exception):
    def __init__(self, kind: ModelErrorKind, message: str = "") -> None:
        super().__init__(message or kind.value)
        self.kind = kind


@dataclass
class ScriptedResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class ModelCallRecord:
    prompt: str
    response_text: str | None = None
    error_kind: ModelErrorKind | None = None


@dataclass
class FakeModelGateway:
    """Queue-driven fake: every request consumes one scripted behavior."""

    _script: deque[ScriptedResponse | FakeModelError] = field(default_factory=deque)
    _calls: list[ModelCallRecord] = field(default_factory=list)

    def enqueue_response(
        self, text: str, prompt_tokens: int = 0, completion_tokens: int = 0
    ) -> None:
        self._script.append(
            ScriptedResponse(
                text=text,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        )

    def enqueue_error(self, kind: ModelErrorKind, message: str = "") -> None:
        self._script.append(FakeModelError(kind, message))

    def request(self, prompt: str) -> ScriptedResponse:
        if not self._script:
            raise AssertionError("no scripted model behavior; enqueue one first")
        item = self._script.popleft()
        if isinstance(item, FakeModelError):
            self._calls.append(ModelCallRecord(prompt=prompt, error_kind=item.kind))
            raise item
        self._calls.append(ModelCallRecord(prompt=prompt, response_text=item.text))
        return item

    @property
    def calls(self) -> list[ModelCallRecord]:
        return list(self._calls)

    def pending_count(self) -> int:
        return len(self._script)
