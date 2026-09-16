"""Activity lifecycle commands (owned by S2-ACTIVITY-001).

Progress is derived, not stored: an ACTIVE activity's effective
progress is its baked progress plus elapsed phases since start, so
quiet phases advance activities with zero writes and zero model
calls. Only transitions (start/interrupt/resume/complete/cancel)
touch the database. One activity per character at a time; travelers
stay at the origin until completion moves them.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.activities import Activity, effective_progress
from worldsim.domain.enums import ActivityKind, ActivityStatus, LifeStatus
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    CharacterId,
    LocationId,
    WorldId,
    new_activity_id,
)

#: Default durations when the start command pins none.
KIND_DURATIONS = {
    ActivityKind.TRAVEL: 1,
    ActivityKind.REST: 8,
    ActivityKind.TRAIN: 4,
    ActivityKind.WORK: 6,
    ActivityKind.PATROL: 2,
}


@dataclass(frozen=True)
class ActivityResult:
    """The activity plus whether the command changed it."""

    activity: Activity
    changed: bool


def _active_for(activities: list[Activity], character_id: CharacterId) -> Activity | None:
    return next(
        (
            activity
            for activity in activities
            if activity.character_id == character_id and activity.status == ActivityStatus.ACTIVE
        ),
        None,
    )


async def start_activity(
    uow: UnitOfWork,
    world_id: WorldId,
    character_id: CharacterId,
    kind: ActivityKind,
    absolute: int,
    duration_phases: int | None = None,
    to_location_id: LocationId | None = None,
) -> Activity:
    """Begin one activity; travelers resolve their leg first."""
    character = await uow.characters.get(character_id)
    if character.world_id != world_id:
        raise DomainError(ErrorCode.NOT_FOUND, "character is not in this world")
    if character.life_status != LifeStatus.ALIVE:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, "the dead start no activities")
    actives = await uow.activities.list_active_for_world(world_id)
    if _active_for(actives, character_id) is not None:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, "character already has an active activity")
    payload: dict[str, object] = {}
    if kind == ActivityKind.TRAVEL:
        if to_location_id is None:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "travel needs a destination")
        legs = await uow.routes.list_for_world(world_id)
        leg = next(
            (
                route
                for route in legs
                if route.from_location_id == character.location_id
                and route.to_location_id == to_location_id
            ),
            None,
        )
        if leg is None:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, "no route serves this leg")
        duration = leg.duration_phases
        payload = {
            "from_location_id": str(character.location_id),
            "to_location_id": str(to_location_id),
            "route_id": str(leg.id),
            "stamina_cost": leg.stamina_cost,
        }
    else:
        if to_location_id is not None:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "only travel takes a destination")
        duration = duration_phases or KIND_DURATIONS[kind]
        if duration < 1:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "duration needs a phase")
    activity = Activity(
        id=new_activity_id(),
        world_id=world_id,
        character_id=character_id,
        kind=kind,
        status=ActivityStatus.ACTIVE,
        start_absolute=absolute,
        duration_phases=duration,
        payload=payload,
    )
    await uow.activities.add(activity)
    await uow.commit()
    return activity


async def interrupt_activity(uow: UnitOfWork, activity_id: UUID, absolute: int) -> ActivityResult:
    """Freeze an active activity, baking elapsed phases into progress."""
    activity = await uow.activities.get(activity_id)
    if activity.status != ActivityStatus.ACTIVE:
        return ActivityResult(activity=activity, changed=False)
    frozen = activity.model_copy(
        update={
            "status": ActivityStatus.INTERRUPTED,
            "progress_phases": effective_progress(activity, absolute),
        }
    )
    saved = await uow.activities.save(frozen, activity.version)
    await uow.commit()
    return ActivityResult(activity=saved, changed=True)


async def resume_activity(uow: UnitOfWork, activity_id: UUID, absolute: int) -> ActivityResult:
    """Restart an interrupted activity from the current phase."""
    activity = await uow.activities.get(activity_id)
    if activity.status != ActivityStatus.INTERRUPTED:
        return ActivityResult(activity=activity, changed=False)
    actives = await uow.activities.list_active_for_world(activity.world_id)
    if _active_for(actives, activity.character_id) is not None:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, "character already has an active activity")
    resumed = activity.model_copy(
        update={"status": ActivityStatus.ACTIVE, "start_absolute": absolute}
    )
    saved = await uow.activities.save(resumed, activity.version)
    await uow.commit()
    return ActivityResult(activity=saved, changed=True)


async def cancel_activity(uow: UnitOfWork, activity_id: UUID) -> ActivityResult:
    """Terminally abandon a planned, active, or interrupted activity."""
    activity = await uow.activities.get(activity_id)
    if activity.status in (ActivityStatus.COMPLETED, ActivityStatus.CANCELLED):
        return ActivityResult(activity=activity, changed=False)
    cancelled = activity.model_copy(update={"status": ActivityStatus.CANCELLED})
    saved = await uow.activities.save(cancelled, activity.version)
    await uow.commit()
    return ActivityResult(activity=saved, changed=True)
