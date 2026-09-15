"""Deterministic random evidence contract (owned by S0-SIM-001).

String seeds keep the underlying generator stable: the same seed, stream,
and bounds always yield the same value, and the evidence record travels
on the event for audit.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

RANDOM_ALGORITHM = "python-random-1"


class RandomEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    seed: int
    stream: str = Field(min_length=1, max_length=64)
    algorithm: str = Field(default=RANDOM_ALGORITHM, min_length=1, max_length=64)
    result: str = Field(min_length=1, max_length=512)


def _generator(seed: int, stream: str) -> random.Random:
    return random.Random(f"{RANDOM_ALGORITHM}:{seed}:{stream}")


def draw_int(seed: int, stream: str, low: int, high: int) -> tuple[int, RandomEvidence]:
    value = _generator(seed, stream).randint(low, high)
    return value, RandomEvidence(seed=seed, stream=stream, result=str(value))


def draw_choice[T](seed: int, stream: str, options: Sequence[T]) -> tuple[T, RandomEvidence]:
    if not options:
        raise ValueError("choice needs at least one option")
    value = _generator(seed, stream).choice(options)
    return value, RandomEvidence(seed=seed, stream=stream, result=str(value))
