"""Role selection, Director proposals, and deity overrides (owned by S2-ROLE-001)."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Request

from worldsim.application.commands.deity import apply_override
from worldsim.application.commands.director import accept_decision
from worldsim.domain.director import DirectorProposal, validate_proposal
from worldsim.domain.enums import LifeStatus, PhaseRunState, UserRole
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_arc_id, new_hook_id, new_role_grant_id
from worldsim.domain.roles import RoleGrant
from worldsim.domain.time import absolute_index
from worldsim.interfaces.http import schemas as api

router = APIRouter(tags=["roles"])


async def effective_role(request: Request, world_id: UUID) -> tuple[str, UUID | None]:
    """Grant-selected role wins; otherwise the request header decides."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        grant = await uow.roles.get_for_world(world_id)
    header_role = request.headers.get("x-worldsim-role", "watcher").lower()
    header_character = request.headers.get("x-worldsim-character")
    if grant is not None:
        return grant.role.value, grant.character_id
    if header_role == "player" and header_character:
        return header_role, UUID(header_character)
    return header_role, None


def require_role(role: str, *allowed: str) -> None:
    if role not in allowed:
        raise DomainError(ErrorCode.FORBIDDEN, f"{role} cannot use this command")


@router.post("/stage2/roles/select", response_model=api.RoleGrantView)
async def select_role(body: api.RoleSelectRequest, request: Request) -> api.RoleGrantView:
    """Select the operating role at a safe boundary (no open run)."""
    try:
        role = UserRole(body.role)
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown role: {body.role}") from exc
    if role == UserRole.PLAYER and body.character_id is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "player needs a character")
    if role != UserRole.PLAYER and body.character_id is not None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "only players bind a character")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        world = await uow.worlds.get(body.world_id)
        if role == UserRole.PLAYER:
            assert body.character_id is not None
            character = await uow.characters.get(body.character_id)
            if character.world_id != body.world_id:
                raise DomainError(ErrorCode.NOT_FOUND, "character is not in this world")
        open_run = await uow.phases.find_open_run(body.world_id)
        if open_run is not None and open_run.state != PhaseRunState.CREATED:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "roles change between phases, not mid-run",
            )
        grant = await uow.roles.set_grant(
            RoleGrant(
                id=new_role_grant_id(),
                world_id=body.world_id,
                role=role,
                character_id=body.character_id,
                granted_absolute=absolute_index(world.day, world.phase),
            )
        )
        await uow.commit()
    return api.RoleGrantView(
        id=grant.id,
        world_id=grant.world_id,
        role=grant.role.value,
        character_id=grant.character_id,
        granted_absolute=grant.granted_absolute,
        version=grant.version,
    )


@router.get("/stage2/roles", response_model=api.RoleGrantView | None)
async def read_role(world_id: UUID, request: Request) -> api.RoleGrantView | None:
    """The active grant, if one was selected."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        grant = await uow.roles.get_for_world(world_id)
    if grant is None:
        return None
    return api.RoleGrantView(
        id=grant.id,
        world_id=grant.world_id,
        role=grant.role.value,
        character_id=grant.character_id,
        granted_absolute=grant.granted_absolute,
        version=grant.version,
    )


@router.post("/stage2/director/proposals", response_model=api.DirectorProposalView)
async def propose(body: api.DirectorProposalRequest, request: Request) -> api.DirectorProposalView:
    """A user Director proposal through the same validation as model ones."""
    role, _viewer = await effective_role(request, body.world_id)
    require_role(role, "director")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        characters = await uow.characters.list_for_world(body.world_id)
        known = frozenset(c.id for c in characters if c.life_status == LifeStatus.ALIVE)
        active_hooks = await uow.narrative.count_active_hooks(body.world_id)
        active_arcs = await uow.narrative.count_active_arcs(body.world_id)
    proposal = DirectorProposal(
        action=f"propose_{body.kind}",
        title=body.title,
        purpose=body.purpose,
        requested_powers=list(body.requested_powers),
        participant_ids=list(body.participant_ids),
    )
    decision = validate_proposal(
        proposal,
        body.world_id,
        known,
        active_hooks,
        active_arcs,
        new_hook_id(),
        new_arc_id(),
    )
    if not decision.accepted:
        raise DomainError(ErrorCode.VALIDATION_FAILED, decision.reason)
    async with state.uow_factory()() as uow:
        world = await uow.worlds.get(body.world_id)
        await accept_decision(
            uow,
            body.world_id,
            decision,
            "director",
            f"director-user:{uuid4().hex}",
            absolute_index(world.day, world.phase),
        )
    assert decision.hook is not None or decision.arc is not None
    row = decision.hook if decision.hook is not None else decision.arc
    assert row is not None
    return api.DirectorProposalView(
        id=row.id,
        world_id=body.world_id,
        kind=body.kind,
        title=row.title,
        reason="accepted",
    )


@router.post("/stage2/deity/overrides", response_model=api.DeityOverrideView)
async def override(body: api.DeityOverrideRequest, request: Request) -> api.DeityOverrideView:
    """A typed deity patch through one audited canonical commit."""
    role, _viewer = await effective_role(request, body.world_id)
    require_role(role, "deity")
    try:
        life_status = LifeStatus(body.life_status) if body.life_status else None
    except ValueError as exc:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, f"unknown life status: {body.life_status}"
        ) from exc
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        run = await uow.phases.latest_run(body.world_id)
        if run is None:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, "deity needs a phase context")
        world = await uow.worlds.get(body.world_id)
        now = absolute_index(world.day, world.phase)
    event_id = await apply_override(
        state.uow_factory(),
        body.world_id,
        body.character_id,
        run.id,
        now,
        stamina=body.stamina,
        mana=body.mana,
        life_status=life_status,
        conditions=body.conditions,
        retcon=body.retcon,
    )
    return api.DeityOverrideView(
        event_id=event_id,
        world_id=body.world_id,
        character_id=body.character_id,
        retcon=body.retcon,
    )
