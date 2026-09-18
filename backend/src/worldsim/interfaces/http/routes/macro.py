"""Stage 5 generation reads and macro advance (owned by S5-UI-001).

Runs, lineage, focus, eras, and endings are public world facts:
watchers and players read them alike. Era digests are
perspective-owned like diaries: players read only their own.
Advancing the clock is an operator action: watcher only.
"""

from __future__ import annotations

from functools import partial
from uuid import UUID

from fastapi import APIRouter, Query, Request

from worldsim.application.capabilities import (
    Capability,
    is_omniscient,
    parse_role,
    require_capability,
)
from worldsim.application.conditions import active_conditions
from worldsim.application.execution import guarded, new_owner
from worldsim.application.macro.endings import evaluate_endings
from worldsim.application.macro.engine import MacroEngine
from worldsim.application.macro.eras import compose_era
from worldsim.application.macro.genealogy import apply_schedule_consequence, assign_focus
from worldsim.application.macro.salience import find_break
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.domain.enums import FocusSlot, MacroResolution, ScheduleStatus
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.routes.roles import effective_role, require_role

router = APIRouter(tags=["macro"])


def _engine_of(request: Request) -> MacroEngine:
    state = request.app.state.app_state
    factory = state.uow_factory()
    return MacroEngine(factory, CanonicalTransaction(factory))


@router.get("/macro/runs", response_model=api.MacroRunsResponse)
async def macro_runs(world_id: UUID, request: Request) -> api.MacroRunsResponse:
    role, _ = await effective_role(request, world_id)
    require_role(role, "watcher", "player", "director", "deity")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        runs = await uow.macro.list_runs(world_id)
        views: list[api.MacroRunView] = []
        for run in runs:
            effects = await uow.macro.list_effects(run.id)
            interruptions = await uow.macro.list_interruptions(run.id)
            views.append(
                api.MacroRunView(
                    run_id=run.id,
                    start_absolute=run.start_absolute,
                    end_absolute=run.end_absolute,
                    resolution=run.resolution.value,
                    state=run.state.value,
                    effects=[
                        api.MacroEffectView(
                            kind=effect.kind.value,
                            detail=effect.detail,
                            event_id=effect.event_id,
                            target_ids=effect.target_ids,
                        )
                        for effect in effects
                    ],
                    interruptions=[
                        api.MacroInterruptionView(
                            at_absolute=item.at_absolute,
                            reason=item.reason.value,
                            detail=item.detail,
                        )
                        for item in interruptions
                    ],
                )
            )
    return api.MacroRunsResponse(world_id=world_id, runs=views)


@router.get("/macro/lineage", response_model=api.LineageResponse)
async def lineage(world_id: UUID, request: Request) -> api.LineageResponse:
    role, _ = await effective_role(request, world_id)
    require_role(role, "watcher", "player", "director", "deity")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        records = await uow.lineage.list_records(world_id)
        names = {record.character_id: record.character_id for record in records}
        characters = await uow.characters.list_for_world(world_id)
        for character in characters:
            names[character.id] = character.name
        links: list[api.LineageLinkView] = []
        for record in records:
            for link in await uow.lineage.list_children(world_id, record.character_id):
                links.append(
                    api.LineageLinkView(
                        parent_id=link.parent_id,
                        parent_name=str(names.get(link.parent_id, link.parent_id)),
                        child_id=link.child_id,
                        child_name=str(names.get(link.child_id, link.child_id)),
                        birth_absolute=link.birth_absolute,
                    )
                )
    return api.LineageResponse(
        world_id=world_id,
        links=links,
        records=[
            api.LineageRecordView(
                character_id=record.character_id,
                name=str(names.get(record.character_id, record.character_id)),
                birth_absolute=record.birth_absolute,
                death_absolute=record.death_absolute,
                life_status=record.life_status.value,
                succession_eligible=record.succession_eligible,
            )
            for record in records
        ],
    )


@router.get("/macro/focus", response_model=api.FocusResponse)
async def focus(world_id: UUID, request: Request) -> api.FocusResponse:
    role, _ = await effective_role(request, world_id)
    require_role(role, "watcher", "player", "director", "deity")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        characters = await uow.characters.list_for_world(world_id)
        names = {character.id: character.name for character in characters}
        assignments: list[api.FocusAssignmentView] = []
        for slot in FocusSlot:
            for item in await uow.lineage.list_focus(world_id, slot):
                from_name = names.get(item.from_character_id) if item.from_character_id else None
                assignments.append(
                    api.FocusAssignmentView(
                        slot=item.slot.value,
                        version=item.version,
                        from_character_id=item.from_character_id,
                        from_name=from_name,
                        to_character_id=item.to_character_id,
                        to_name=str(names.get(item.to_character_id, item.to_character_id)),
                        effective_absolute=item.effective_absolute,
                        reason=item.reason,
                    )
                )
    assignments.sort(key=lambda item: (item.slot, item.version))
    return api.FocusResponse(world_id=world_id, assignments=assignments)


@router.get("/macro/eras", response_model=api.ErasResponse)
async def eras(
    world_id: UUID,
    request: Request,
    start_absolute: int = Query(default=0, ge=0),
    end_absolute: int = Query(default=3600, ge=1),
    owner_id: UUID | None = None,
) -> api.ErasResponse:
    role, viewer = await effective_role(request, world_id)
    require_role(role, "watcher", "player", "director", "deity")
    if not is_omniscient(parse_role(role)) and owner_id is not None and viewer != owner_id:
        raise DomainError(ErrorCode.FORBIDDEN, "era digests are holder-private")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        digests = await uow.macro.list_eras_for_span(world_id, start_absolute, end_absolute)
    if not is_omniscient(parse_role(role)):
        digests = [era for era in digests if viewer is not None and era.owner_id == viewer]
    if owner_id is not None:
        digests = [era for era in digests if era.owner_id == owner_id]
    return api.ErasResponse(
        world_id=world_id,
        eras=[
            api.EraView(
                era_id=era.id,
                owner_id=era.owner_id,
                start_absolute=era.start_absolute,
                end_absolute=era.end_absolute,
                text=era.text,
                source_ids=era.source_ids,
                version=era.version,
            )
            for era in digests
        ],
    )


@router.get("/macro/endings", response_model=api.EndingsResponse)
async def endings(world_id: UUID, request: Request) -> api.EndingsResponse:
    role, _ = await effective_role(request, world_id)
    require_role(role, "watcher", "player", "director", "deity")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        rows = await uow.macro.list_endings(world_id)
    return api.EndingsResponse(
        world_id=world_id,
        endings=[
            api.EndingView(
                kind=row.kind.value,
                satisfied=row.satisfied,
                evaluated_absolute=row.evaluated_absolute,
                window_start_absolute=row.window_start_absolute,
                evidence_event_ids=[event_id.hex for event_id in row.evidence_event_ids],
                detail=row.detail,
            )
            for row in rows
        ],
    )


@router.post("/macro/advance", response_model=api.MacroAdvanceResponse)
async def macro_advance(
    body: api.MacroAdvanceRequest, request: Request
) -> api.MacroAdvanceResponse:
    role, _ = await effective_role(request, body.world_id)
    require_capability(parse_role(role), Capability.MACRO)
    try:
        resolution = MacroResolution(body.resolution)
    except ValueError as exc:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, f"unknown resolution: {body.resolution}"
        ) from exc
    engine = _engine_of(request)
    state = request.app.state.app_state
    factory = state.uow_factory()
    pending = await active_conditions(factory, body.world_id)
    if pending:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            "active world conditions must resolve before macro advance: "
            + ", ".join(c.public_label for c in pending),
        )

    async def _hook(world_id: UUID, start: int, end: int) -> int | None:
        return await find_break(factory, world_id, start, end)

    result = await guarded(
        factory,
        body.world_id,
        "macro",
        new_owner("http"),
        None,
        partial(
            engine.advance_period,
            body.world_id,
            body.day,
            resolution,
            salience_break=_hook,
            on_schedule_fire=apply_schedule_consequence,
        ),
    )
    return api.MacroAdvanceResponse(
        run_id=result.run.id,
        state=result.run.state.value,
        start_absolute=result.run.start_absolute,
        end_absolute=result.run.end_absolute,
        event_ids=result.event_ids,
        duplicate=result.duplicate,
    )


@router.post("/macro/eras/compose", response_model=api.EraView)
async def compose_era_view(body: api.EraComposeRequest, request: Request) -> api.EraView:
    role, viewer = await effective_role(request, body.world_id)
    require_role(role, "watcher", "player", "director", "deity")
    if not is_omniscient(parse_role(role)) and viewer != body.owner_id:
        raise DomainError(ErrorCode.FORBIDDEN, "era digests are holder-private")
    state = request.app.state.app_state
    try:
        era = await compose_era(
            state.uow_factory(),
            body.world_id,
            body.owner_id,
            body.start_absolute,
            body.end_absolute,
        )
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, str(exc)) from exc
    return api.EraView(
        era_id=era.id,
        owner_id=era.owner_id,
        start_absolute=era.start_absolute,
        end_absolute=era.end_absolute,
        text=era.text,
        source_ids=era.source_ids,
        version=era.version,
    )


@router.post("/macro/endings/evaluate", response_model=api.EndingsResponse)
async def evaluate_endings_view(
    body: api.EndingsEvaluateRequest, request: Request
) -> api.EndingsResponse:
    role, _ = await effective_role(request, body.world_id)
    require_capability(parse_role(role), Capability.MACRO)
    state = request.app.state.app_state
    rows = await evaluate_endings(state.uow_factory(), body.world_id, body.at_absolute)
    return api.EndingsResponse(
        world_id=body.world_id,
        endings=[
            api.EndingView(
                kind=row.kind.value,
                satisfied=row.satisfied,
                evaluated_absolute=row.evaluated_absolute,
                window_start_absolute=row.window_start_absolute,
                evidence_event_ids=[event_id.hex for event_id in row.evidence_event_ids],
                detail=row.detail,
            )
            for row in rows
        ],
    )


@router.post("/macro/focus/assign", response_model=api.FocusAssignmentView)
async def assign_focus_view(
    body: api.FocusAssignRequest, request: Request
) -> api.FocusAssignmentView:
    role, _ = await effective_role(request, body.world_id)
    require_capability(parse_role(role), Capability.MACRO)
    try:
        slot = FocusSlot(body.slot)
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown slot: {body.slot}") from exc
    state = request.app.state.app_state
    assignment = await assign_focus(
        state.uow_factory(),
        body.world_id,
        slot,
        body.to_character_id,
        body.reason,
        body.effective_absolute,
        from_character_id=body.from_character_id,
    )
    async with state.uow_factory()() as uow:
        characters = await uow.characters.list_for_world(body.world_id)
        names = {character.id: character.name for character in characters}
    from_name = names.get(assignment.from_character_id) if assignment.from_character_id else None
    return api.FocusAssignmentView(
        slot=assignment.slot.value,
        version=assignment.version,
        from_character_id=assignment.from_character_id,
        from_name=from_name,
        to_character_id=assignment.to_character_id,
        to_name=str(names.get(assignment.to_character_id, assignment.to_character_id)),
        effective_absolute=assignment.effective_absolute,
        reason=assignment.reason,
    )


@router.post("/macro/schedules/{schedule_id}/cancel", response_model=api.ScheduleCancelResponse)
async def cancel_schedule(schedule_id: UUID, request: Request) -> api.ScheduleCancelResponse:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        schedule = await uow.schedules.get(schedule_id)
        role, _ = await effective_role(request, schedule.world_id)
        require_capability(parse_role(role), Capability.MACRO)
        if schedule.status != ScheduleStatus.PENDING:
            return api.ScheduleCancelResponse(schedule_id=schedule.id, status=schedule.status.value)
        saved = await uow.schedules.save(
            schedule.model_copy(update={"status": ScheduleStatus.CANCELLED}),
            schedule.version,
        )
        await uow.commit()
    return api.ScheduleCancelResponse(schedule_id=saved.id, status=saved.status.value)
