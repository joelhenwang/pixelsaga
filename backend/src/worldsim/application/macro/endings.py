"""Deterministic end-condition evaluation (owned by S5-END-001).

Three terminal questions, all answerable from stored rows:

- sustained peace: a full configured window with no recorded deaths
  and no salient schedule fires. One calm scene can never satisfy it:
  a short history fails the window-length check first.
- eradication: no living characters left.
- maximum day: the clock reached the configured last day.

Every evaluation persists its evidence row, satisfied or not, so
ending decisions stay auditable. The first satisfied evaluation also
commits one world-ended event and marks the world ended; later calls
find the ended status and skip the final event.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from worldsim.application.macro.eras import window_events
from worldsim.application.transactions.canonical import UnitOfWorkFactory
from worldsim.domain.enums import EndConditionKind, EventType, LifeStatus, WorldStatus
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.events import WorldEvent
from worldsim.domain.ids import new_end_evidence_id
from worldsim.domain.macro import EndConditionEvidence
from worldsim.domain.time import PHASES_PER_DAY

#: Default peace window: 300 phases (30 days, one game-month of quiet).
#: Long enough that a single calm scene or a lucky week can never
#: satisfy it, short enough to fit inside one macro year.
DEFAULT_PEACE_WINDOW_PHASES = 300
PEACE_WINDOW_KEY = "ending.peace_window_phases"
MAX_DAY_KEY = "ending.max_day"


def _window_phases(config: dict[str, object]) -> int:
    if PEACE_WINDOW_KEY not in config:
        return DEFAULT_PEACE_WINDOW_PHASES
    try:
        window = int(config[PEACE_WINDOW_KEY])  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, f"world config {PEACE_WINDOW_KEY} must be an integer"
        ) from None
    if window < 1:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"world config {PEACE_WINDOW_KEY} too small")
    return window


def _max_day(config: dict[str, object]) -> int | None:
    if MAX_DAY_KEY not in config:
        return None
    try:
        limit = int(config[MAX_DAY_KEY])  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, f"world config {MAX_DAY_KEY} must be an integer"
        ) from None
    if limit < 1:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"world config {MAX_DAY_KEY} too small")
    return limit


async def evaluate_endings(
    factory: UnitOfWorkFactory, world_id: UUID, at_absolute: int
) -> list[EndConditionEvidence]:
    async with factory() as uow:
        config = await uow.worlds.get_config(world_id)
        window = _window_phases(config)
        max_day = _max_day(config)
        window_start = max(0, at_absolute - window)

        deaths = await uow.lineage.list_deaths(world_id, window_start, at_absolute)
        salient = [
            event.id
            for event in await window_events(uow, world_id, window_start, at_absolute)
            if event.event_type == EventType.SCHEDULE_FIRED
            and event.summary.get("salient") == "true"
        ]
        living = [
            character
            for character in await uow.characters.list_for_world(world_id)
            if character.life_status == LifeStatus.ALIVE
        ]

        rows: list[EndConditionEvidence] = []
        if not living:
            rows.append(
                EndConditionEvidence(
                    id=new_end_evidence_id(),
                    world_id=world_id,
                    kind=EndConditionKind.CIVILIZATION_ERADICATED,
                    evaluated_absolute=at_absolute,
                    window_start_absolute=at_absolute,
                    satisfied=True,
                    detail=f"{len(deaths)} recorded deaths in the peace window, none living",
                )
            )
        elif at_absolute - window_start < window:
            rows.append(
                EndConditionEvidence(
                    id=new_end_evidence_id(),
                    world_id=world_id,
                    kind=EndConditionKind.SUSTAINED_PEACE,
                    evaluated_absolute=at_absolute,
                    window_start_absolute=window_start,
                    satisfied=False,
                    detail=(
                        f"only {at_absolute - window_start} phases elapsed, peace needs {window}"
                    ),
                )
            )
        elif deaths or salient:
            rows.append(
                EndConditionEvidence(
                    id=new_end_evidence_id(),
                    world_id=world_id,
                    kind=EndConditionKind.SUSTAINED_PEACE,
                    evaluated_absolute=at_absolute,
                    window_start_absolute=window_start,
                    satisfied=False,
                    evidence_event_ids=salient,
                    detail=(
                        f"{len(deaths)} deaths and {len(salient)} major events inside the window"
                    ),
                )
            )
        else:
            rows.append(
                EndConditionEvidence(
                    id=new_end_evidence_id(),
                    world_id=world_id,
                    kind=EndConditionKind.SUSTAINED_PEACE,
                    evaluated_absolute=at_absolute,
                    window_start_absolute=window_start,
                    satisfied=True,
                    detail=f"no deaths and no major events across {window} phases",
                )
            )

        if max_day is None:
            rows.append(
                EndConditionEvidence(
                    id=new_end_evidence_id(),
                    world_id=world_id,
                    kind=EndConditionKind.MAXIMUM_DAY,
                    evaluated_absolute=at_absolute,
                    window_start_absolute=at_absolute,
                    satisfied=False,
                    detail="no maximum day configured",
                )
            )
        else:
            day_start = (max_day - 1) * PHASES_PER_DAY
            rows.append(
                EndConditionEvidence(
                    id=new_end_evidence_id(),
                    world_id=world_id,
                    kind=EndConditionKind.MAXIMUM_DAY,
                    evaluated_absolute=at_absolute,
                    window_start_absolute=min(day_start, at_absolute),
                    satisfied=at_absolute >= day_start,
                    detail=f"clock at phase {at_absolute}, last day {max_day} starts {day_start}",
                )
            )

        for row in rows:
            await uow.macro.save_end(row)

        if any(row.satisfied for row in rows):
            world = await uow.worlds.get(world_id)
            if world.status == WorldStatus.ACTIVE:
                sequence = await uow.events.max_sequence(world_id) + 1
                kinds = ",".join(sorted(r.kind.value for r in rows if r.satisfied))
                await uow.events.append_event(
                    WorldEvent(
                        id=uuid4(),
                        world_id=world_id,
                        sequence=sequence,
                        event_type=EventType.WORLD_ENDED,
                        absolute_index=at_absolute,
                        phase_run_id=None,
                        summary={"kinds": kinds},
                    )
                )
                await uow.worlds.save(
                    world.model_copy(update={"status": WorldStatus.ENDED}), world.version
                )
        await uow.commit()
        return rows
