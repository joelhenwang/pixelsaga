"""Stage 2 claim and belief reads and assertions (owned by S2-KNOW-001)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request

from worldsim.application.commands.knowledge import assert_claim
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.time import absolute_index
from worldsim.interfaces.http import schemas as api

router = APIRouter(tags=["knowledge"])


@router.post("/stage2/claims", response_model=api.ClaimView)
async def voice_claim(body: api.ClaimRequest, request: Request) -> api.ClaimView:
    """Voice a proposition; eligible listeners fold beliefs."""
    role = request.headers.get("x-worldsim-role", "watcher").lower()
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        world = await uow.worlds.get(body.world_id)
        now = absolute_index(world.day, world.phase)
    async with state.uow_factory()() as uow:
        claim = await assert_claim(
            uow,
            role,
            body.world_id,
            body.speaker_id,
            body.proposition,
            body.audience_location_id,
            now,
            refutes_claim_id=body.refutes_claim_id,
        )
    return api.ClaimView(
        id=claim.id,
        world_id=claim.world_id,
        speaker_id=claim.speaker_id,
        audience_location_id=claim.audience_location_id,
        proposition=claim.proposition,
        refutes_claim_id=claim.refutes_claim_id,
        version=claim.version,
    )


@router.get("/stage2/claims", response_model=api.ClaimListResponse)
async def list_claims(world_id: UUID, viewer_id: UUID, request: Request) -> api.ClaimListResponse:
    """Only claims the viewer could have heard: global or co-located."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        viewer = await uow.characters.get(viewer_id)
        claims = await uow.knowledge.list_claims_for_world(world_id)
    heard = [
        claim
        for claim in claims
        if claim.audience_location_id is None or claim.audience_location_id == viewer.location_id
    ]
    return api.ClaimListResponse(
        world_id=world_id,
        viewer_id=viewer_id,
        members=[
            api.ClaimView(
                id=claim.id,
                world_id=claim.world_id,
                speaker_id=claim.speaker_id,
                audience_location_id=claim.audience_location_id,
                proposition=claim.proposition,
                refutes_claim_id=claim.refutes_claim_id,
                version=claim.version,
            )
            for claim in heard
        ],
    )


@router.get("/stage2/beliefs", response_model=api.BeliefListResponse)
async def list_beliefs(world_id: UUID, holder_id: UUID, request: Request) -> api.BeliefListResponse:
    """Beliefs are private: holders and watchers only."""
    role = request.headers.get("x-worldsim-role", "watcher").lower()
    viewer = request.headers.get("x-worldsim-character")
    if role != "watcher" and viewer != str(holder_id):
        raise DomainError(ErrorCode.FORBIDDEN, "beliefs are holder-private")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        beliefs = await uow.knowledge.list_beliefs_for_holder(world_id, holder_id)
    return api.BeliefListResponse(
        world_id=world_id,
        holder_id=holder_id,
        members=[
            api.BeliefView(
                id=belief.id,
                world_id=belief.world_id,
                holder_id=belief.holder_id,
                proposition=belief.proposition,
                confidence=belief.confidence,
                last_touched_absolute=belief.last_touched_absolute,
                version=belief.version,
            )
            for belief in beliefs
        ],
    )
