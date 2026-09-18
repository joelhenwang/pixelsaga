"""Story catalog, original setup, and creation drafts (owned by MAINMENU-A03).

One story is one runtime World: the route ID is the world UUID. Setup
snapshots are immutable and read-only; drafts carry typed nonsecret JSON.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request

from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_story_draft_id
from worldsim.domain.stories import (
    DraftPayload,
    DraftStep,
    StoryCatalogEntry,
    StoryDraft,
)
from worldsim.domain.time import absolute_index, utcnow
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.routes.roles import effective_role

router = APIRouter(tags=["stories"])

_VALID_ROLES = ("player", "watcher", "director", "deity")
_VALID_STEPS = ("world", "characters", "mode", "story", "ai", "review")


async def _summary(request: Request, world_id: UUID) -> api.StorySummary:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        entry = await uow.stories.get_catalog(world_id)
        world = await uow.worlds.get(world_id)
        role, viewer = await effective_role(request, world_id)
    if role == "player" and viewer is not None:
        mode = "player"
    else:
        mode = role
    status = world.status.value if hasattr(world.status, "value") else str(world.status)
    phase = world.phase.value if hasattr(world.phase, "value") else str(world.phase)
    return api.StorySummary(
        story_id=world_id,
        world_id=world_id,
        title=entry.title,
        world_name=world.name,
        mode=mode,
        day=world.day,
        phase=phase,
        absolute_index=absolute_index(world.day, world.phase),
        last_played_at=entry.last_played_at,
        archived=entry.archived_at is not None,
        status=status,
    )


@router.get("/stories", response_model=api.StoryListResponse)
async def list_stories(
    request: Request,
    status: str = "in_progress",
    q: str | None = None,
    sort: str = "recent",
    cursor: str | None = None,
    limit: int = 20,
) -> api.StoryListResponse:
    """Paginated catalog; search filters one bounded page without a cursor."""
    if status not in ("in_progress", "completed", "archived", "all"):
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown status: {status}")
    if sort not in ("recent", "title"):
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown sort: {sort}")
    archived: bool | None = None
    if status == "archived":
        archived = True
    elif status in ("in_progress", "completed"):
        archived = False
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        if q:
            entries = await uow.stories.list_catalog(archived=None, limit=100)
        else:
            entries = await uow.stories.list_catalog(
                archived=archived, limit=max(1, min(limit, 100)), cursor=cursor
            )
    items: list[api.StorySummary] = []
    for entry in entries:
        summary = await _summary(request, entry.world_id)
        if status == "in_progress" and summary.status != "active":
            continue
        if status == "completed" and (summary.status == "active" or summary.archived):
            continue
        if status == "archived" and not summary.archived:
            continue
        if q and q.lower() not in summary.title.lower():
            continue
        items.append(summary)
    if sort == "title":
        items.sort(key=lambda item: (item.title.lower(), str(item.story_id)))
    if q:
        items = items[: max(1, min(limit, 100))]
        next_cursor = None
    else:
        next_cursor = _cursor_for(entries[-1]) if len(entries) == max(1, min(limit, 100)) else None
        items = items[: max(1, min(limit, 100))]
    return api.StoryListResponse(items=items, next_cursor=next_cursor)


def _cursor_for(entry: StoryCatalogEntry) -> str:
    stamp = entry.last_played_at.isoformat() if entry.last_played_at else ""
    return f"{stamp}|{entry.world_id.hex}"


@router.get("/stories/{story_id}", response_model=api.StoryDetail)
async def read_story(story_id: UUID, request: Request) -> api.StoryDetail:
    summary = await _summary(request, story_id)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        entry = await uow.stories.get_catalog(story_id)
    return api.StoryDetail(
        story_id=summary.story_id,
        world_id=summary.world_id,
        title=summary.title,
        world_name=summary.world_name,
        mode=summary.mode,
        day=summary.day,
        phase=summary.phase,
        absolute_index=summary.absolute_index,
        last_played_at=summary.last_played_at,
        archived_at=entry.archived_at,
        status=summary.status,
        metadata_version=entry.metadata_version,
    )


@router.get("/stories/{story_id}/setup", response_model=api.StorySetupView)
async def read_setup(story_id: UUID, request: Request) -> api.StorySetupView:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        setup = await uow.stories.get_setup(story_id)
    return api.StorySetupView(
        story_id=story_id,
        world_id=story_id,
        schema_version=setup.schema_version,
        provenance=setup.provenance.value,
        payload=dict(setup.payload),
        content_hash=setup.content_hash,
        created_at=setup.created_at,
    )


@router.get("/stories/{story_id}/setup/export")
async def export_setup(story_id: UUID, request: Request) -> dict:
    """Redacted setup export: resolved configuration, never a save backup."""
    view = await read_setup(story_id, request)
    return {
        "schema_version": 1,
        "kind": "story-setup-export",
        "story_id": str(view.story_id),
        "provenance": view.provenance,
        "payload": view.payload,
        "content_hash": view.content_hash,
    }


@router.patch("/stories/{story_id}", response_model=api.StoryDetail)
async def rename_story(
    story_id: UUID, body: api.StoryPatchRequest, request: Request
) -> api.StoryDetail:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        entry = await uow.stories.get_catalog(story_id)
        update = entry.model_copy(
            update={
                "title": body.title or entry.title,
                "cover_asset_id": (
                    body.cover_asset_id if body.cover_asset_id is not None else entry.cover_asset_id
                ),
            }
        )
        await uow.stories.save_catalog(update, body.expected_version)
        await uow.commit()
    return await read_story(story_id, request)


@router.post("/stories/{story_id}/open", response_model=api.StoryDetail)
async def open_story(story_id: UUID, request: Request) -> api.StoryDetail:
    """Record an explicit successful open; safe to retry, never advances."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        entry = await uow.stories.get_catalog(story_id)
        await uow.worlds.get(story_id)
        await uow.stories.save_catalog(
            entry.model_copy(update={"last_played_at": utcnow()}),
            entry.metadata_version,
        )
        await uow.commit()
    return await read_story(story_id, request)


@router.post("/stories/{story_id}/archive", response_model=api.StoryDetail)
async def archive_story(
    story_id: UUID, body: api.StoryArchiveRequest, request: Request
) -> api.StoryDetail:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        entry = await uow.stories.get_catalog(story_id)
        if await uow.phases.find_open_run(story_id) is not None:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "pause or finish the open run before archiving",
            )
        await uow.stories.save_catalog(
            entry.model_copy(update={"archived_at": utcnow()}),
            body.expected_version,
        )
        await uow.commit()
    return await read_story(story_id, request)


@router.post("/stories/{story_id}/unarchive", response_model=api.StoryDetail)
async def unarchive_story(
    story_id: UUID, body: api.StoryArchiveRequest, request: Request
) -> api.StoryDetail:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        entry = await uow.stories.get_catalog(story_id)
        await uow.stories.save_catalog(
            entry.model_copy(update={"archived_at": None}),
            body.expected_version,
        )
        await uow.commit()
    return await read_story(story_id, request)


def _draft_view(draft: StoryDraft) -> api.StoryDraftView:
    payload = draft.payload.model_dump(mode="json")
    return api.StoryDraftView(
        id=draft.id,
        payload=api.StoryDraftPayload.model_validate(payload),
        current_step=draft.current_step.value,
        version=draft.version,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
        created_world_id=draft.created_world_id,
    )


def _parse_draft_payload(body: api.StoryDraftPayload) -> DraftPayload:
    try:
        present = {
            key: value for key, value in body.model_dump(mode="json").items() if value is not None
        }
        return DraftPayload.model_validate(present)
    except Exception as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"invalid draft: {exc}") from exc


@router.get("/story-drafts", response_model=list[api.StoryDraftView])
async def list_drafts(request: Request, limit: int = 20) -> list[api.StoryDraftView]:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        drafts = await uow.stories.list_drafts(max(1, min(limit, 100)))
    return [_draft_view(draft) for draft in drafts]


@router.post("/story-drafts", response_model=api.StoryDraftView)
async def create_draft(body: api.StoryDraftCreateRequest, request: Request) -> api.StoryDraftView:
    if body.current_step not in _VALID_STEPS:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown step: {body.current_step}")
    payload = _parse_draft_payload(body.payload)
    now = utcnow()
    draft = StoryDraft(
        id=new_story_draft_id(),
        payload=payload,
        current_step=DraftStep(body.current_step),
        version=1,
        created_at=now,
        updated_at=now,
    )
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await uow.stories.add_draft(draft)
        await uow.commit()
    return _draft_view(draft)


@router.get("/story-drafts/{draft_id}", response_model=api.StoryDraftView)
async def read_draft(draft_id: UUID, request: Request) -> api.StoryDraftView:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        return _draft_view(await uow.stories.get_draft(draft_id))


@router.patch("/story-drafts/{draft_id}", response_model=api.StoryDraftView)
async def save_draft(
    draft_id: UUID, body: api.StoryDraftPatchRequest, request: Request
) -> api.StoryDraftView:
    if body.current_step not in _VALID_STEPS:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown step: {body.current_step}")
    payload = _parse_draft_payload(body.payload)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        draft = await uow.stories.get_draft(draft_id)
        if draft.created_world_id is not None:
            raise DomainError(ErrorCode.FORBIDDEN, "a consumed draft is read-only")
        saved = await uow.stories.save_draft(
            draft.model_copy(
                update={
                    "payload": payload,
                    "current_step": DraftStep(body.current_step),
                    "updated_at": utcnow(),
                }
            ),
            body.expected_version,
        )
        await uow.commit()
    return _draft_view(saved)


@router.delete("/story-drafts/{draft_id}")
async def delete_draft(draft_id: UUID, request: Request) -> dict[str, str]:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await uow.stories.delete_draft(draft_id)
        await uow.commit()
    return {"id": str(draft_id), "state": "deleted"}


@router.post("/story-drafts/{draft_id}/validate", response_model=api.DraftValidationView)
async def validate_draft(draft_id: UUID, request: Request) -> api.DraftValidationView:
    """Full validation plus effective preview; never mutates or generates."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        draft = await uow.stories.get_draft(draft_id)
        issues = _validate(draft.payload)
        resolved: dict = {}
        if draft.payload.world.preset_id is not None:
            try:
                revision = draft.payload.world.preset_revision or 1
                preset = await uow.presets.get_revision(draft.payload.world.preset_id, revision)
                resolved["world"] = preset.payload.model_dump(mode="json")
            except DomainError as exc:
                issues.append(f"world preset unreadable: {exc}")
        for member in draft.payload.cast:
            if member.preset_id is None:
                continue
            try:
                revision = member.preset_revision or 1
                preset = await uow.presets.get_revision(member.preset_id, revision)
                resolved[member.instance_key] = preset.payload.model_dump(mode="json")
            except DomainError as exc:
                issues.append(f"cast preset unreadable for {member.instance_key}: {exc}")
    return api.DraftValidationView(valid=not issues, issues=issues, resolved=resolved)


def _validate(payload: DraftPayload) -> list[str]:
    issues: list[str] = []
    keys = [member.instance_key for member in payload.cast]
    if len(set(keys)) != len(keys):
        issues.append("cast instance keys must be unique")
    if not payload.cast:
        issues.append("select at least one character")
    if payload.mode.role not in _VALID_ROLES:
        issues.append(f"unknown role: {payload.mode.role}")
    if payload.mode.role == "player":
        if not payload.mode.controlled_cast_key:
            issues.append("player mode needs a controlled cast member")
        elif payload.mode.controlled_cast_key not in keys:
            issues.append("controlled character is not in the cast")
    return issues
