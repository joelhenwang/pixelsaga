"""Deterministic operational and fictional clocks (owned by S0-QA-001)."""

from __future__ import annotations

PHASES: tuple[str, ...] = (
    "dawn",
    "sunrise",
    "morning",
    "noon",
    "afternoon",
    "sunset",
    "dusk",
    "evening",
    "night",
    "midnight",
)


class FakeOperationalClock:
    """Controllable wall clock in milliseconds."""

    def __init__(self, start_ms: int = 0) -> None:
        self._now_ms = start_ms

    def now_ms(self) -> int:
        return self._now_ms

    def advance_ms(self, delta_ms: int) -> int:
        if delta_ms < 0:
            raise ValueError("clock cannot advance backwards")
        self._now_ms += delta_ms
        return self._now_ms


class FictionalClock:
    """Ten-phase fictional calendar clock with day rollover."""

    def __init__(self, day: int = 1, phase_index: int = 0) -> None:
        if day < 1:
            raise ValueError("day starts at 1")
        if not 0 <= phase_index < len(PHASES):
            raise ValueError("phase_index out of range")
        self._day = day
        self._phase_index = phase_index

    @property
    def day(self) -> int:
        return self._day

    @property
    def phase_index(self) -> int:
        return self._phase_index

    @property
    def phase(self) -> str:
        return PHASES[self._phase_index]

    def advance_phase(self) -> str:
        self._phase_index += 1
        if self._phase_index >= len(PHASES):
            self._phase_index = 0
            self._day += 1
        return self.phase

    def position(self) -> dict[str, int]:
        return {"day": self._day, "phase_index": self._phase_index}
