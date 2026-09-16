"""Stage 2 activity commands and reads (owned by S2-ACTIVITY-001)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import TypeAdapter

from worldsim.application.commands.activities import (
    cancel_activity,
    interrupt_activity,
    resume_activity,
    start_activity,
)
from worldsim.domain.activities import Activity
from worldsim.domain.enums import ActivityKind
from worldsim.domain.time import absolute_index
from worldsim.interfaces.http import schemas as api

router = APIRouter(tags=["activities"])

_ACTIVITY_ADAPTER: TypeAdapter[api.ActivityStartRequest] = TypeAdapter(api.ActivityStartRequest)


def activity_view(member: Activity) -> api.ActivityView:
    return api.ActivityView(
        id=member.id,
        world_id=member.world_id,
        character_id=member.character_id,
        kind=member.kind.value,
        status=member.status.value,
        start_absolute=member.start_absolute,
        duration_phases=member.duration_phases,
        progress_phases=member.progress_phases,
        version=member.version,
    )


async def _absolute_now(request: Request, world_id: UUID) -> int:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        world = await uow.worlds.get(world_id)
    return absolute_index(world.day, world.phase)


@router.post("/stage2/activities", response_model=api.ActivityView)
async def start(body: api.ActivityStartRequest, request: Request) -> api.ActivityView:
    """Begin one activity for a character (one active at a time)."""
    _ACTIVITY_ADAPTER.validate_python(body)
    state = request.app.state.app_state
    now = await _absolute_now(request, body.world_id)
    async with state.uow_factory()() as uow:
        activity = await start_activity(
            uow,
            body.world_id,
            body.character_id,
            ActivityKind(body.kind),
            now,
            duration_phases=body.duration_phases,
            to_location_id=body.to_location_id,
            skill=body.skill,
        )
    return activity_view(activity)


@router.post("/stage2/activities/{activity_id}/interrupt", response_model=api.ActivityView)
async def interrupt(activity_id: UUID, request: Request) -> api.ActivityView:
    """Freeze an active activity, baking elapsed progress."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        world_id = (await uow.activities.get(activity_id)).world_id
    now = await _absolute_now(request, world_id)
    async with state.uow_factory()() as uow:
        result = await interrupt_activity(uow, activity_id, now)
    return activity_view(result.activity)


@router.post("/stage2/activities/{activity_id}/resume", response_model=api.ActivityView)
async def resume(activity_id: UUID, request: Request) -> api.ActivityView:
    """Restart an interrupted activity from the current phase."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        world_id = (await uow.activities.get(activity_id)).world_id
    now = await _absolute_now(request, world_id)
    async with state.uow_factory()() as uow:
        result = await resume_activity(uow, activity_id, now)
    return activity_view(result.activity)


@router.post("/stage2/activities/{activity_id}/cancel", response_model=api.ActivityView)
async def cancel(activity_id: UUID, request: Request) -> api.ActivityView:
    """Terminally abandon an activity."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        result = await cancel_activity(uow, activity_id)
    return activity_view(result.activity)


@router.get("/stage2/activities", response_model=api.ActivityListResponse)
async def list_activities(world_id: UUID, request: Request) -> api.ActivityListResponse:
    """Active activities for a world, oldest first."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        actives = await uow.activities.list_active_for_world(world_id)
    return api.ActivityListResponse(world_id=world_id, members=[activity_view(a) for a in actives])
