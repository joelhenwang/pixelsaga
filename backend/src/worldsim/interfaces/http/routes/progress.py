"""Stage 2 inventory and skill reads plus item commands (owned by S2-PROGRESS-001)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Request

from worldsim.application.commands.inventory import give_item, transfer_item
from worldsim.domain.items import ItemDefinition, load_item_definitions
from worldsim.domain.progress import ItemInstance
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.routes.roles import effective_role, require_role

router = APIRouter(tags=["progress"])


@lru_cache(maxsize=4)
def _catalog(definitions_dir: str) -> dict[str, ItemDefinition]:
    return load_item_definitions(Path(definitions_dir) / "items.json")


def _catalog_for(request: Request) -> dict[str, ItemDefinition]:
    state = request.app.state.app_state
    definitions = state.seed_dir.parent.parent / "definitions"
    return _catalog(str(definitions))


def _item_view(item: ItemInstance) -> api.ItemView:
    return api.ItemView(
        id=item.id,
        world_id=item.world_id,
        item_key=item.item_key,
        owner_id=item.owner_id,
        quantity=item.quantity,
        version=item.version,
    )


@router.post("/stage2/items/give", response_model=api.ItemView)
async def give(body: api.ItemGiveRequest, request: Request) -> api.ItemView:
    """Create one instance for a holder (or the ground)."""
    role, _viewer = await effective_role(request, body.world_id)
    require_role(role, "watcher", "player")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        item = await give_item(
            uow,
            role,
            body.world_id,
            body.item_key,
            body.owner_id,
            _catalog_for(request),
            body.quantity,
        )
    return _item_view(item)


@router.post("/stage2/items/{item_id}/transfer", response_model=api.ItemView)
async def transfer(item_id: UUID, body: api.ItemTransferRequest, request: Request) -> api.ItemView:
    """Move one instance to a new holder (or drop it)."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        world_id = (await uow.inventory.get_item(item_id)).world_id
    role, _viewer = await effective_role(request, world_id)
    require_role(role, "watcher", "player")
    async with state.uow_factory()() as uow:
        item = await transfer_item(uow, role, item_id, body.to_owner_id)
    return _item_view(item)


@router.get("/stage2/items", response_model=api.ItemListResponse)
async def list_items(
    world_id: UUID, request: Request, owner_id: UUID | None = None
) -> api.ItemListResponse:
    """Instances held by one holder (or lying on the ground)."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        items = await uow.inventory.list_for_owner(world_id, owner_id)
    return api.ItemListResponse(
        world_id=world_id,
        owner_id=owner_id,
        members=[_item_view(item) for item in items],
    )


@router.get("/stage2/skills", response_model=api.SkillListResponse)
async def list_skills(
    world_id: UUID, character_id: UUID, request: Request
) -> api.SkillListResponse:
    """Folded skill progress for one character (read-only; sessions award)."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        skills = await uow.progress.list_skills_for_character(world_id, character_id)
    return api.SkillListResponse(
        world_id=world_id,
        character_id=character_id,
        members=[
            api.SkillView(
                skill_key=skill.skill_key,
                progress=skill.progress,
                sessions=skill.sessions,
                version=skill.version,
            )
            for skill in skills
        ],
    )
