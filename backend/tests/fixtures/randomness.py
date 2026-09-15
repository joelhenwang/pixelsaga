"""Seeded random-source port and fake (owned by S0-QA-001)."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


class SeededRandomSource:
    """Deterministic RNG with stream identity and algorithm version evidence."""

    algorithm_version = "python-random-1"

    def __init__(self, seed: int, stream: str = "default") -> None:
        self.seed = seed
        self.stream = stream
        self._rng = random.Random(seed)

    def integers(self, low: int, high: int) -> int:
        return self._rng.randint(low, high)

    def choice(self, options: Sequence[T]) -> T:
        return self._rng.choice(options)

    def shuffled(self, options: Sequence[T]) -> list[T]:
        items = list(options)
        self._rng.shuffle(items)
        return items

    def evidence(self) -> dict[str, str]:
        return {
            "stream": self.stream,
            "seed": str(self.seed),
            "algorithm_version": self.algorithm_version,
        }
