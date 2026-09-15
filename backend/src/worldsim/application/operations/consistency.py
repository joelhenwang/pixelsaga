"""Stage 0 consistency audit (owned by S0-GATE-001).

Re-derives every deterministic ID from the world clock and checks the
durable chain: contiguous event sequences, dense effect ordinals, run
and task coherence per index, snapshot presence and latest-hash
agreement, and no stale open runs. Reads through repository ports only;
writes nothing. A clean world reports zero violations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from worldsim.application.orchestration.service import (
    derive_run_id,
    derive_snapshot_id,
    task_key_for,
)
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.enums import PhaseRunState
from worldsim.domain.time import absolute_index


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


@dataclass(frozen=True)
class AuditViolation:
    check: str
    detail: str


@dataclass(frozen=True)
class AuditReport:
    world_id: UUID
    checks_run: int
    violations: tuple[AuditViolation, ...] = field(default_factory=tuple)

    @property
    def clean(self) -> bool:
        return not self.violations


async def audit_world(uow_factory: UnitOfWorkFactory, world_id: UUID) -> AuditReport:
    violations: list[AuditViolation] = []
    checks = 0

    async with uow_factory() as uow:
        world = await uow.worlds.get(world_id)
        clock = absolute_index(world.day, world.phase)
        total = await uow.events.count_events(world_id)
        checks += 1
        entries = await uow.events.list_range(world_id, 0, total + 1)
        sequences = [event.sequence for event in entries]
        if sequences != list(range(1, total + 1)):
            violations.append(
                AuditViolation("event_sequences", f"expected 1..{total}, saw {sequences}")
            )
        checks += 1
        if entries:
            latest = entries[-1]
            if latest.absolute_index != clock:
                violations.append(
                    AuditViolation(
                        "clock_cursor",
                        f"clock={clock} latest_event={latest.absolute_index}",
                    )
                )
        for event in entries:
            checks += 1
            effects = await uow.events.list_effects(event.id)
            ordinals = [effect.ordinal for effect in effects]
            if ordinals != list(range(len(effects))):
                violations.append(
                    AuditViolation("effect_ordinals", f"event {event.sequence}: {ordinals}")
                )
        for index in range(1, clock + 1):
            checks += 1
            run_id = derive_run_id(world_id, index)
            try:
                run = await uow.phases.get_run(run_id)
            except Exception as exc:
                violations.append(
                    AuditViolation("run_presence", f"index {index}: {type(exc).__name__}")
                )
                continue
            if run.state != PhaseRunState.COMPLETED:
                violations.append(
                    AuditViolation("run_completed", f"index {index}: {run.state.value}")
                )
            task = await uow.tasks.find_by_key(world_id, task_key_for(index))
            if task is None:
                violations.append(AuditViolation("task_presence", f"index {index}"))
            elif run.state == PhaseRunState.COMPLETED and task.state.value != "succeeded":
                violations.append(
                    AuditViolation(
                        "task_coherence", f"index {index}: run completed, task {task.state.value}"
                    )
                )
            try:
                snapshot = await uow.phases.get_snapshot(derive_snapshot_id(run_id))
            except Exception as exc:
                violations.append(
                    AuditViolation("snapshot_presence", f"index {index}: {type(exc).__name__}")
                )
                continue
            checks += 1
            if snapshot.absolute_index != index or snapshot.phase_run_id != run_id:
                violations.append(AuditViolation("snapshot_linkage", f"index {index}"))
            if index == clock:
                checks += 1
                if snapshot.world_version != world.version:
                    violations.append(
                        AuditViolation(
                            "snapshot_currency",
                            f"snapshot={snapshot.world_version} world={world.version}",
                        )
                    )
                characters = await uow.characters.list_for_world(world_id)
                staged = {character.id.hex: character.version for character in characters}
                sealed = {member.character_id.hex: member.version for member in snapshot.characters}
                if staged != sealed:
                    violations.append(AuditViolation("snapshot_members", f"index {index}"))
        checks += 1
        open_run = await uow.phases.find_open_run(world_id)
        if open_run is not None and open_run.absolute_index <= clock:
            violations.append(
                AuditViolation(
                    "stale_open_run",
                    f"run {open_run.id} index {open_run.absolute_index} clock {clock}",
                )
            )
    return AuditReport(world_id=world_id, checks_run=checks, violations=tuple(violations))
