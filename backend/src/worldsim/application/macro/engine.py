"""Deterministic macro engine (owned by S5-MACRO-001).

A macro period advances a quiet interval at reduced resolution with no
model calls. Only established deterministic rules run: the clock tick,
due schedule fires, and clock-derived activity progress (completions
commit on the next detailed tick through the existing path). There is
no passive recovery and no invented physics: a month without rest
leaves resources exactly where detailed rules put them.

Every sub-step is idempotent, so a crash resumes by re-running the
period: the clock commit dedupes on its idempotency key, fired
schedules skip on APPLIED status, and the run row replays once
COMPLETED. An interruption writes no state at all; detailed
simulation resumes at the untouched clock.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

from worldsim.application.transactions.canonical import (
    CanonicalTransaction,
    CommitRequest,
    UnitOfWorkFactory,
    canonical_input_hash,
)
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.effects import AdvanceClockEffect
from worldsim.domain.enums import (
    EventType,
    InterruptionReason,
    MacroResolution,
    MacroRunState,
    ScheduleStatus,
    WorldStatus,
)
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.events import WorldEvent
from worldsim.domain.ids import (
    derive_macro_effect_id,
    derive_macro_run_id,
    new_macro_interruption_id,
)
from worldsim.domain.macro import (
    SALIENT_SCHEDULE_FLAG,
    MacroAggregateEffect,
    MacroEffectKind,
    MacroInterruption,
    MacroPeriodRun,
    resolution_range,
)
from worldsim.domain.schedules import ScheduledEffect
from worldsim.domain.time import absolute_index

SalienceBreak = Callable[[UUID, int, int], Awaitable[int | None]]
"""Predicate hook (owned by S5-SALIENCE-001): absolute break point in [start, end), if any."""
ScheduleFireHook = Callable[[UnitOfWork, ScheduledEffect], Awaitable[list[UUID]]]
"""Consequence hook (owned by S5-GENEALOGY-001): runs inside the fire
transaction so consequence rows commit atomically with the fired event.
Returns affected character IDs, recorded on the aggregate row."""


@dataclass(frozen=True)
class MacroResult:
    run: MacroPeriodRun
    event_ids: list[UUID]
    duplicate: bool


class MacroEngine:
    def __init__(
        self,
        factory: UnitOfWorkFactory,
        canonical: CanonicalTransaction,
    ) -> None:
        self._factory = factory
        self._canonical = canonical

    async def advance_period(
        self,
        world_id: UUID,
        day: int,
        resolution: MacroResolution,
        *,
        salience_break: SalienceBreak | None = None,
        on_schedule_fire: ScheduleFireHook | None = None,
    ) -> MacroResult:
        start, end = resolution_range(day, resolution)
        run_id = derive_macro_run_id(world_id, start, end, resolution.value)

        resuming = False
        async with self._factory() as uow:
            try:
                run = await uow.macro.get_run(run_id)
                resuming = run.state == MacroRunState.RUNNING
            except DomainError:
                run = MacroPeriodRun(
                    id=run_id,
                    world_id=world_id,
                    start_absolute=start,
                    end_absolute=end,
                    resolution=resolution,
                    state=MacroRunState.RUNNING,
                    seed=0,
                )
                await uow.macro.create_run(run)
                await uow.commit()
            else:
                if run.state == MacroRunState.COMPLETED:
                    effects = await uow.macro.list_effects(run_id)
                    return MacroResult(
                        run=run,
                        event_ids=[e.event_id for e in effects if e.event_id is not None],
                        duplicate=True,
                    )
                if run.state == MacroRunState.INTERRUPTED:
                    run = await self._maybe_resume(uow, run, world_id, start, end, salience_break)
                    if run.state == MacroRunState.INTERRUPTED:
                        return MacroResult(run=run, event_ids=[], duplicate=True)
                    resuming = True

            world = await uow.worlds.get(world_id)
            if world.status != WorldStatus.ACTIVE:
                raise DomainError(ErrorCode.PRECONDITION_FAILED, f"world is {world.status.value}")
            clock = absolute_index(world.day, world.phase)
            # A resumed run may find the clock already advanced past its
            # own tick: the clock commit dedupes on its idempotency key,
            # so re-entry heals the remaining steps instead of doubling.
            if clock != start and not (resuming and clock == end):
                raise DomainError(
                    ErrorCode.PRECONDITION_FAILED,
                    f"macro must continue the live clock: clock={clock} start={start}",
                )
            world_version = world.version
            await uow.commit()

        if salience_break is not None:
            at = await salience_break(world_id, start, end)
            if at is not None and start <= at < end:
                return await self._interrupt(run, at, "seeded break inside the period")

        clock_event_id = await self._commit_clock(run, world_version)
        fired = await self._fire_due_schedules(run, on_schedule_fire)

        async with self._factory() as uow:
            run = await uow.macro.get_run(run_id)
            event_ids = [clock_event_id, *[schedule_id for schedule_id, _ in fired]]
            existing = {
                (effect.kind.value, effect.event_id)
                for effect in await uow.macro.list_effects(run_id)
            }
            candidates = [
                MacroAggregateEffect(
                    id=derive_macro_effect_id(
                        run_id, MacroEffectKind.CLOCK_ADVANCE.value, clock_event_id
                    ),
                    run_id=run_id,
                    world_id=world_id,
                    kind=MacroEffectKind.CLOCK_ADVANCE,
                    detail=f"{resolution.value} period {start} to {end}",
                    event_id=clock_event_id,
                )
            ]
            for schedule_id, targets in fired:
                candidates.append(
                    MacroAggregateEffect(
                        id=derive_macro_effect_id(
                            run_id, MacroEffectKind.SCHEDULE_PROGRESS.value, schedule_id
                        ),
                        run_id=run_id,
                        world_id=world_id,
                        kind=MacroEffectKind.SCHEDULE_PROGRESS,
                        target_ids=targets,
                        detail=f"schedule {schedule_id.hex} fired at its due phase",
                        event_id=schedule_id,
                    )
                )
            for effect in candidates:
                if (effect.kind.value, effect.event_id) not in existing:
                    await uow.macro.add_effect(effect)
            completed = await uow.macro.save_run(
                run.model_copy(update={"state": MacroRunState.COMPLETED}), run.version
            )
            await uow.commit()
        return MacroResult(run=completed, event_ids=event_ids, duplicate=False)

    async def _maybe_resume(
        self,
        uow: UnitOfWork,
        run: MacroPeriodRun,
        world_id: UUID,
        start: int,
        end: int,
        salience_break: SalienceBreak | None,
    ) -> MacroPeriodRun:
        """Re-evaluate an interruption: proceed when the break is gone.

        Cancelling the blocking schedule must unblock the exact period;
        otherwise interruption rows become tombstones that fragment the
        aggregate history into ever-smaller runs. A still-blocked
        period returns as-is with no new row.
        """
        if salience_break is None:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "macro run interrupted; resume detailed simulation first",
            )
        at = await salience_break(world_id, start, end)
        if at is not None and start <= at < end:
            return await uow.macro.get_run(run.id)
        current = await uow.macro.get_run(run.id)
        resumed = await uow.macro.save_run(
            current.model_copy(update={"state": MacroRunState.RUNNING}), current.version
        )
        await uow.commit()
        return resumed

    async def _interrupt(self, run: MacroPeriodRun, at: int, detail: str) -> MacroResult:
        async with self._factory() as uow:
            current = await uow.macro.get_run(run.id)
            known = {item.at_absolute for item in await uow.macro.list_interruptions(run.id)}
            if at not in known:
                await uow.macro.add_interruption(
                    MacroInterruption(
                        id=new_macro_interruption_id(),
                        run_id=run.id,
                        world_id=run.world_id,
                        at_absolute=at,
                        reason=InterruptionReason.SEEDED_EVENT,
                        detail=detail,
                    )
                )
            interrupted = await uow.macro.save_run(
                current.model_copy(update={"state": MacroRunState.INTERRUPTED}),
                current.version,
            )
            await uow.commit()
        return MacroResult(run=interrupted, event_ids=[], duplicate=False)

    async def _commit_clock(self, run: MacroPeriodRun, world_version: int) -> UUID:
        key = f"macro:{run.id.hex}:clock"
        async with self._factory() as uow:
            command_id = await uow.commands.get_by_key(run.world_id, key)
            if command_id is not None:
                event_id = await uow.commands.get_result(command_id)
                assert event_id is not None, "committed clock must link its event"
                return event_id
        effect = AdvanceClockEffect(
            affected_ids=[run.world_id],
            expected_versions={str(run.world_id): world_version},
            from_index=run.start_absolute,
            to_index=run.end_absolute,
        )
        payload: dict[str, object] = {
            "run_id": run.id.hex,
            "resolution": run.resolution.value,
            "start_absolute": run.start_absolute,
            "end_absolute": run.end_absolute,
        }
        result = await self._canonical.commit(
            CommitRequest(
                command_id=uuid4(),
                world_id=run.world_id,
                idempotency_key=key,
                actor_role="system",
                command_type="macro_tick",
                expected_versions={str(run.world_id): world_version},
                payload=payload,
                input_hash=canonical_input_hash(
                    {"key": key, "payload": payload, "effects": [effect.model_dump(mode="json")]}
                ),
                absolute_index=run.end_absolute - 1,
                phase_run_id=None,
                event_type=EventType.MACRO_TICKED,
                effects=[effect],
            )
        )
        return result.event_id

    async def _fire_due_schedules(
        self, run: MacroPeriodRun, on_schedule_fire: ScheduleFireHook | None
    ) -> list[tuple[UUID, list[UUID]]]:
        """Fire pending schedules due through the period; applied rows never refire.

        Schedules due before the window start fire late with a marker
        rather than vanishing: the clock already moved past their due
        phase, but dropping them would erase seeded consequences.
        """
        async with self._factory() as uow:
            due = await uow.schedules.list_due(run.world_id, run.end_absolute - 1)
            fired: list[tuple[UUID, list[UUID]]] = []
            for schedule in due:
                sequence = await uow.events.max_sequence(run.world_id) + 1
                await uow.events.append_event(
                    WorldEvent(
                        id=schedule.id,
                        world_id=run.world_id,
                        sequence=sequence,
                        event_type=EventType.SCHEDULE_FIRED,
                        absolute_index=schedule.due_absolute,
                        phase_run_id=None,
                        summary={
                            "kind": schedule.kind,
                            "due": str(schedule.due_absolute),
                            "macro_run": run.id.hex,
                            "late": (
                                "true" if schedule.due_absolute < run.start_absolute else "false"
                            ),
                            "salient": (
                                "true"
                                if schedule.payload.get(SALIENT_SCHEDULE_FLAG) is True
                                else "false"
                            ),
                        },
                    )
                )
                await uow.schedules.save(
                    schedule.model_copy(update={"status": ScheduleStatus.APPLIED}),
                    schedule.version,
                )
                targets: list[UUID] = []
                if on_schedule_fire is not None:
                    targets = await on_schedule_fire(uow, schedule)
                fired.append((schedule.id, targets))
            await uow.commit()
            return fired
