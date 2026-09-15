"""Process-boundary and fault-injection hooks (owned by S0-QA-001)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Generator
from contextlib import contextmanager


class FaultHooks:
    """Named fault flags plus callbacks at process boundaries."""

    def __init__(self) -> None:
        self._flags: dict[str, bool] = {}
        self._callbacks: dict[str, list[Callable[[], None]]] = defaultdict(list)

    def is_set(self, name: str) -> bool:
        return self._flags.get(name, False)

    @contextmanager
    def inject(self, name: str) -> Generator[None, None, None]:
        self._flags[name] = True
        try:
            yield
        finally:
            self._flags[name] = False

    def on(self, boundary: str, callback: Callable[[], None]) -> None:
        self._callbacks[boundary].append(callback)

    def run(self, boundary: str) -> int:
        callbacks = list(self._callbacks.get(boundary, []))
        for callback in callbacks:
            callback()
        return len(callbacks)
