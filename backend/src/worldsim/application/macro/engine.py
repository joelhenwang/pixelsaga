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
    derive_macro_run_id,
    new_macro_aggregate_effect_id,
    new_macro_interruption_id,
)
from worldsim.domain.macro import (
    MacroAggregateEffect,
    MacroEffectKind,
    MacroInterruption,
    MacroPeriodRun,
    resolution_range,
)
from worldsim.domain.time import absolute_index

SalienceBreak = Callable[[UUID, int, int], Awaitable[int | None]]
"""Predicate hook (owned by S5-SALIENCE-001): absolute break point in [start, end), if any."""


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
        seed: int = 0,
    ) -> MacroResult:
        start, end = resolution_range(day, resolution)
        run_id = derive_macro_run_id(world_id, start, end, resolution.value)

        async with self._factory() as uow:
            try:
                run = await uow.macro.get_run(run_id)
            except DomainError:
                run = MacroPeriodRun(
                    id=run_id,
                    world_id=world_id,
                    start_absolute=start,
                    end_absolute=end,
                    resolution=resolution,
                    state=MacroRunState.RUNNING,
                    seed=seed,
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
                    raise DomainError(
                        ErrorCode.PRECONDITION_FAILED,
                        "macro run interrupted; resume detailed simulation first",
                    )

            world = await uow.worlds.get(world_id)
            if world.status != WorldStatus.ACTIVE:
                raise DomainError(ErrorCode.PRECONDITION_FAILED, f"world is {world.status.value}")
            if absolute_index(world.day, world.phase) != start:
                raise DomainError(
                    ErrorCode.PRECONDITION_FAILED,
                    "macro must continue the live clock: "
                    f"clock={absolute_index(world.day, world.phase)} start={start}",
                )
            world_version = world.version
            await uow.commit()

        if salience_break is not None:
            at = await salience_break(world_id, start, end)
            if at is not None and start <= at < end:
                return await self._interrupt(run, at, "seeded break inside the period")

        clock_event_id = await self._commit_clock(run, world_version)
        fired = await self._fire_due_schedules(run)

        async with self._factory() as uow:
            run = await uow.macro.get_run(run_id)
            event_ids = [clock_event_id, *fired]
            await uow.macro.add_effect(
                MacroAggregateEffect(
                    id=new_macro_aggregate_effect_id(),
                    run_id=run_id,
                    world_id=world_id,
                    kind=MacroEffectKind.CLOCK_ADVANCE,
                    detail=f"{resolution.value} period {start} to {end}",
                    event_id=clock_event_id,
                )
            )
            for schedule_id in fired:
                await uow.macro.add_effect(
                    MacroAggregateEffect(
                        id=new_macro_aggregate_effect_id(),
                        run_id=run_id,
                        world_id=world_id,
                        kind=MacroEffectKind.SCHEDULE_PROGRESS,
                        detail=f"schedule {schedule_id.hex} fired at its due phase",
                        event_id=schedule_id,
                    )
                )
            completed = await uow.macro.save_run(
                run.model_copy(update={"state": MacroRunState.COMPLETED}), run.version
            )
            await uow.commit()
        return MacroResult(run=completed, event_ids=event_ids, duplicate=False)

    async def _interrupt(self, run: MacroPeriodRun, at: int, detail: str) -> MacroResult:
        async with self._factory() as uow:
            current = await uow.macro.get_run(run.id)
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
                absolute_index=run.end_absolute,
                phase_run_id=None,
                event_type=EventType.MACRO_TICKED,
                effects=[effect],
            )
        )
        return result.event_id

    async def _fire_due_schedules(self, run: MacroPeriodRun) -> list[UUID]:
        """Fire pending schedules due inside the period; applied rows never refire."""
        async with self._factory() as uow:
            due = [
                schedule
                for schedule in await uow.schedules.list_due(run.world_id, run.end_absolute - 1)
                if schedule.due_absolute >= run.start_absolute
            ]
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
                        participant_ids=[],
                        summary={
                            "kind": schedule.kind,
                            "due": str(schedule.due_absolute),
                            "macro_run": run.id.hex,
                        },
                    )
                )
                await uow.schedules.save(
                    schedule.model_copy(update={"status": ScheduleStatus.APPLIED}),
                    schedule.version,
                )
            await uow.commit()
            return [schedule.id for schedule in due]
