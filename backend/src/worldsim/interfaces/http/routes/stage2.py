"""Stage 2 perspective-aware reads (owned by S2-API-001).

Timeline, map, diary, character activities, hooks/arcs, and
operations status. Watchers see everything; players see public
facts plus their own participation. Hooks and arcs stay
director-side: players learn of them through scenes, never here.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Request

from worldsim.application.capabilities import is_omniscient, parse_role
from worldsim.domain.enums import Visibility
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.routes.activities import activity_view
from worldsim.interfaces.http.routes.roles import effective_role, require_role

router = APIRouter(tags=["stage2"])


async def _role_of(request: Request, world_id: UUID) -> tuple[str, UUID | None]:
    return await effective_role(request, world_id)


@router.get("/stage2/timeline", response_model=api.TimelineResponse)
async def timeline(
    world_id: UUID,
    request: Request,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> api.TimelineResponse:
    """Committed events with narration snippets, newest last.

    `next_after` is the last scanned source sequence, not the last
    displayed entry: a page with zero visible entries still advances.
    """
    role, viewer = await _role_of(request, world_id)
    omniscient = is_omniscient(parse_role(role))
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        events = await uow.events.list_range(world_id, after, limit)
        entries: list[api.TimelineEntry] = []
        for event in events:
            if not omniscient and (
                event.visibility != Visibility.PUBLIC
                and (viewer is None or viewer not in event.participant_ids)
            ):
                continue
            beats = await uow.scenes.narrations_for_event(event.id)
            entries.append(
                api.TimelineEntry(
                    sequence=event.sequence,
                    event_id=event.id,
                    event_type=event.event_type.value,
                    absolute_index=event.absolute_index,
                    snippet=" ".join(b.text for b in beats)[:160] or None,
                )
            )
        total = await uow.events.count_events(world_id)
        high = await uow.events.max_sequence(world_id)
    scanned = events[-1].sequence if events else after
    return api.TimelineResponse(
        world_id=world_id,
        entries=entries,
        total=total,
        next_after=scanned,
        has_more=high > scanned,
    )


@router.get("/stage2/map", response_model=api.MapResponse)
async def world_map(world_id: UUID, request: Request) -> api.MapResponse:
    """Places, routes, and occupants; players see discovered ground only."""
    role, viewer = await _role_of(request, world_id)
    omniscient = is_omniscient(parse_role(role))
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        locations = await uow.locations.list_for_world(world_id)
        characters = await uow.characters.list_for_world(world_id)
    places: list[api.MapPlace] = []
    for location in locations:
        if (
            not omniscient
            and not location.discovered
            and (
                viewer is None
                or all(c.location_id != location.id for c in characters if c.id == viewer)
            )
        ):
            continue
        present = [c for c in characters if c.location_id == location.id]
        places.append(
            api.MapPlace(
                id=location.id,
                name=location.name,
                region=location.region,
                discovered=location.discovered,
                routes=[
                    api.MapRoute(
                        to_location_id=route.destination_location_id,
                        duration_phases=route.duration_phases,
                    )
                    for route in location.routes
                ],
                occupants=[character.name for character in present],
                occupant_ids=[character.id for character in present],
            )
        )
    return api.MapResponse(world_id=world_id, places=places)


@router.get("/stage2/characters/{character_id}/diary", response_model=api.DiaryResponse)
async def diary(character_id: UUID, request: Request) -> api.DiaryResponse:
    """One owner's observations, memories, summaries, and digests. Holder or watcher."""
    role, viewer = await _effective_viewer(request, character_id)
    require_role(role, "watcher", "player")
    if role != "watcher" and viewer != character_id:
        raise DomainError(ErrorCode.FORBIDDEN, "diaries are holder-private")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        character = await uow.characters.get(character_id)
        observations = await uow.perception.observations_for_observer(character_id, 50)
        memories = await uow.perception.memories_for_owner(character_id)
        summaries = await uow.summaries.list_for_owner(character.world_id, character_id)
        digests = await uow.digests.list_for_owner(character.world_id, character_id)
    return api.DiaryResponse(
        character_id=character_id,
        observations=[
            api.DiaryEntry(
                kind="observation",
                phase=obs.created_phase_index,
                text="; ".join(f"{fact.key}: {fact.value}" for fact in obs.facts),
            )
            for obs in observations
        ],
        memories=[
            api.DiaryEntry(kind="memory", phase=mem.created_phase_index, text=mem.text)
            for mem in memories
        ],
        summaries=[
            api.DiaryEntry(kind="summary", phase=s.day * 10 - 1, text=s.text) for s in summaries
        ],
        digests=[
            api.DiaryEntry(kind="digest", phase=d.created_phase_index, text=d.text) for d in digests
        ],
    )


async def _effective_viewer(request: Request, character_id: UUID) -> tuple[str, UUID | None]:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        character = await uow.characters.get(character_id)
    return await _role_of(request, character.world_id)


@router.get(
    "/stage2/characters/{character_id}/activities",
    response_model=api.ActivityListResponse,
)
async def character_activities(character_id: UUID, request: Request) -> api.ActivityListResponse:
    """One character's undertakings, oldest first."""
    role, viewer = await _effective_viewer(request, character_id)
    require_role(role, "watcher", "player")
    if role != "watcher" and viewer != character_id:
        raise DomainError(ErrorCode.FORBIDDEN, "activities are holder-private")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        character = await uow.characters.get(character_id)
        activities = await uow.activities.list_for_character(character.world_id, character_id)
    return api.ActivityListResponse(
        world_id=character.world_id,
        members=[activity_view(a) for a in activities],
    )


@router.get("/stage2/director/hooks", response_model=api.HookListResponse)
async def director_hooks(world_id: UUID, request: Request) -> api.HookListResponse:
    """Open opportunities. Director-side: players learn through scenes."""
    role, _viewer = await _role_of(request, world_id)
    require_role(role, "watcher", "director")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        hooks = await uow.narrative.list_hooks_for_world(world_id)
        arcs = await uow.narrative.list_arcs_for_world(world_id)
    return api.HookListResponse(
        world_id=world_id,
        hooks=[api.HookView(id=h.id, title=h.title, status=h.status.value) for h in hooks],
        arcs=[api.ArcView(id=a.id, title=a.title, status=a.status.value) for a in arcs],
    )


@router.get("/stage2/operations/status", response_model=api.OperationsStatus)
async def operations_status(world_id: UUID, request: Request) -> api.OperationsStatus:
    """Counts only: open runs, pending outbox, committed events."""
    role, _viewer = await _role_of(request, world_id)
    require_role(role, "watcher", "director", "player")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        open_run = await uow.phases.find_open_run(world_id)
        pending = await uow.outbox.count_pending(world_id)
        total = await uow.events.count_events(world_id)
    return api.OperationsStatus(
        world_id=world_id,
        open_run_id=open_run.id if open_run else None,
        open_run_state=open_run.state.value if open_run else None,
        pending_outbox=pending,
        total_events=total,
    )
