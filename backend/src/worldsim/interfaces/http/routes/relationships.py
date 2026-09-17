"""Stage 2 relationship reads and evidence commands (owned by S2-REL-001)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request

from worldsim.application.commands.relationships import record_evidence
from worldsim.domain.enums import RelationshipDimension
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.relationships import Relationship, describe
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.routes.roles import effective_role, require_role

router = APIRouter(tags=["relationships"])


def _relationship_view(
    relationship: Relationship, names: dict[UUID, str], character_id: UUID
) -> api.RelationshipView:
    outgoing = relationship.source_id == character_id
    other = relationship.target_id if outgoing else relationship.source_id
    return api.RelationshipView(
        id=relationship.id,
        world_id=relationship.world_id,
        source_id=relationship.source_id,
        target_id=relationship.target_id,
        direction="outgoing" if outgoing else "incoming",
        trust=relationship.trust,
        affection=relationship.affection,
        respect=relationship.respect,
        summary=describe(relationship, names.get(other, other.hex[:8])),
        version=relationship.version,
    )


@router.post("/stage2/relationships/evidence", response_model=api.RelationshipView)
async def record(body: api.RelationshipEvidenceRequest, request: Request) -> api.RelationshipView:
    """Fold one directional evidence delta into the projection."""
    role, viewer = await effective_role(request, body.world_id)
    require_role(role, "watcher", "player")
    if role == "player" and viewer != body.source_id:
        raise DomainError(ErrorCode.FORBIDDEN, "players record only their own evidence")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        relationship = await record_evidence(
            uow,
            role,
            body.world_id,
            body.source_id,
            body.target_id,
            RelationshipDimension(body.dimension),
            body.delta,
            body.note,
        )
        names = {
            character.id: character.name
            for character in await uow.characters.list_for_world(body.world_id)
        }
    return _relationship_view(relationship, names, body.source_id)


@router.get("/stage2/relationships", response_model=api.RelationshipListResponse)
async def list_relationships(
    world_id: UUID, character_id: UUID, request: Request
) -> api.RelationshipListResponse:
    """Both directions around one character, labeled by direction."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        relationships = await uow.relationships.list_for_character(world_id, character_id)
        names = {
            character.id: character.name
            for character in await uow.characters.list_for_world(world_id)
        }
    return api.RelationshipListResponse(
        world_id=world_id,
        character_id=character_id,
        members=[
            _relationship_view(relationship, names, character_id) for relationship in relationships
        ],
    )
