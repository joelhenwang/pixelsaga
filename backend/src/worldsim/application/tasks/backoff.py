"""Deterministic retry backoff (owned by S0-TASK-001).

Exponential without jitter: the same attempt always waits the same
seconds, so retries stay reproducible across restarts.
"""

from __future__ import annotations

BASE_S = 5.0
CAP_S = 600.0


def backoff_s(attempt: int) -> float:
    """Seconds to wait before the given 1-based attempt runs."""
    if attempt < 1:
        raise ValueError("attempt starts at 1")
    return min(CAP_S, BASE_S * (2.0 ** (attempt - 1)))
