"""Quiet-interval selection and salience breaks (owned by S5-SALIENCE-001).

Selection is deterministic and model-free: it reads pending schedules
inside each candidate window and the world policy, nothing else.
A schedule carrying the salient payload flag is a seeded major event;
macro never fires past one. Either the window is ineligible (the
caller stays detailed) or the engine interrupts exactly at its due
phase through ``find_break``.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from worldsim.application.transactions.canonical import UnitOfWorkFactory
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.enums import MacroResolution, MacroRunState
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.macro import (
    SALIENT_SCHEDULE_FLAG,
    MacroPolicy,
    resolution_range,
)

POLICY_PENDING_KEY = "macro.max_pending_schedules"
POLICY_WINDOW_KEY = "macro.max_window_phases"

_LARGEST_FIRST = (
    MacroResolution.YEAR,
    MacroResolution.MONTH,
    MacroResolution.WEEK,
    MacroResolution.DAY,
)


def _policy_from_config(config: dict[str, object]) -> MacroPolicy:
    updates: dict[str, int] = {}
    for key, field in (
        (POLICY_PENDING_KEY, "max_pending_schedules"),
        (POLICY_WINDOW_KEY, "max_window_phases"),
    ):
        if key in config:
            try:
                updates[field] = int(config[key])  # type: ignore[arg-type]
            except (TypeError, ValueError):
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED, f"world config {key} must be an integer"
                ) from None
    try:
        return MacroPolicy(**updates)
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"invalid macro policy: {exc}") from exc


async def load_policy(uow: UnitOfWork, world_id: UUID) -> MacroPolicy:
    return _policy_from_config(await uow.worlds.get_config(world_id))


@dataclass(frozen=True)
class WindowReport:
    eligible: bool
    reasons: list[str]
    salient_due: int | None
    pending: int


async def check_window(
    uow: UnitOfWork, world_id: UUID, start: int, end: int, policy: MacroPolicy
) -> WindowReport:
    reasons: list[str] = []
    if end - start > policy.max_window_phases:
        reasons.append(f"window spans {end - start} phases, cap is {policy.max_window_phases}")
    due = [
        schedule
        for schedule in await uow.schedules.list_due(world_id, end - 1)
        if schedule.due_absolute >= start
    ]
    if len(due) > policy.max_pending_schedules:
        reasons.append(f"{len(due)} pending schedules, cap is {policy.max_pending_schedules}")
    salient = [s.due_absolute for s in due if s.payload.get(SALIENT_SCHEDULE_FLAG) is True]
    if salient:
        reasons.append(f"seeded major event due at phase {min(salient)}")
    return WindowReport(
        eligible=not reasons,
        reasons=reasons,
        salient_due=min(salient) if salient else None,
        pending=len(due),
    )


async def select_resolution(
    factory: UnitOfWorkFactory, world_id: UUID, day: int, policy: MacroPolicy | None = None
) -> MacroResolution | None:
    """Largest eligible resolution covering ``day``; None means stay detailed."""
    async with factory() as uow:
        resolved = policy if policy is not None else await load_policy(uow, world_id)
        for resolution in _LARGEST_FIRST:
            start, end = resolution_range(day, resolution)
            report = await check_window(uow, world_id, start, end, resolved)
            if report.eligible:
                return resolution
    return None


async def find_break(
    factory: UnitOfWorkFactory, world_id: UUID, start: int, end: int
) -> int | None:
    """Engine hook: earliest seeded major event due inside [start, end), if any."""
    async with factory() as uow:
        policy = await load_policy(uow, world_id)
        report = await check_window(uow, world_id, start, end, policy)
        return report.salient_due


async def macro_covers(factory: UnitOfWorkFactory, world_id: UUID, index: int) -> bool:
    """Whether a completed macro run ends exactly at ``index`` (detailed may resume)."""
    async with factory() as uow:
        run = await uow.macro.find_covering_run(world_id, index)
        return run is not None and run.state == MacroRunState.COMPLETED
