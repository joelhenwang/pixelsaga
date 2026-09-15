"""Stage scenario harness skeleton (owned by S0-QA-001)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ScenarioStep:
    name: str
    action: Callable[[], object]


class StageScenario:
    """Ordered named steps with collected evidence.

    S0-GATE-001 owns the full deterministic scenario; this skeleton proves
    the step/evidence shape that later stages extend.
    """

    def __init__(self, name: str = "stage-scenario") -> None:
        self.name = name
        self._steps: list[ScenarioStep] = []

    def add_step(self, name: str, action: Callable[[], object]) -> None:
        self._steps.append(ScenarioStep(name=name, action=action))

    def run(self) -> dict[str, object]:
        records: list[dict[str, object]] = []
        for step in self._steps:
            records.append({"name": step.name, "result": step.action()})
        return {
            "scenario": self.name,
            "step_count": len(records),
            "steps": records,
        }
