"""Claim assertion with listener eligibility and belief folding (owned by S2-KNOW-001).

Hearing is positional: co-located living characters form beliefs,
everyone else never sees the claim. The speaker stands behind their
own words; listeners start doubtful and reinforce on repetition. A
refuting claim halves confidence in the refuted proposition without
deleting anything. Canon is untouched: no effects, no projections,
only claim/belief rows beside the audit command.
"""

from __future__ import annotations

from uuid import uuid4

from worldsim.application.transactions.canonical import canonical_input_hash
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.characters import Character
from worldsim.domain.enums import LifeStatus
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    CharacterId,
    ClaimId,
    EventId,
    LocationId,
    WorldId,
    new_belief_id,
    new_claim_id,
)
from worldsim.domain.knowledge import (
    FIRST_HEARING,
    SPEAKER_HOLD,
    Belief,
    Claim,
    contradict,
    normalize,
    reinforce,
)


async def _eligible_listeners(
    uow: UnitOfWork, world_id: WorldId, audience: LocationId | None
) -> list[Character]:
    characters = await uow.characters.list_for_world(world_id)
    return [
        character
        for character in characters
        if character.life_status == LifeStatus.ALIVE
        and (audience is None or character.location_id == audience)
    ]


async def assert_claim(
    uow: UnitOfWork,
    actor_role: str,
    world_id: WorldId,
    speaker_id: CharacterId,
    proposition: str,
    audience_location_id: LocationId | None,
    absolute: int,
    refutes_claim_id: ClaimId | None = None,
    source_event_id: EventId | None = None,
) -> Claim:
    """Voice a proposition; eligible listeners fold beliefs."""
    speaker = await uow.characters.get(speaker_id)
    if speaker.world_id != world_id:
        raise DomainError(ErrorCode.NOT_FOUND, "speaker is not in this world")
    if speaker.life_status != LifeStatus.ALIVE:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, "the dead assert nothing")
    text = normalize(proposition)
    if not text:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "claims need a proposition")
    refuted: Claim | None = None
    if refutes_claim_id is not None:
        refuted = await uow.knowledge.get_claim(refutes_claim_id)
        if refuted.world_id != world_id:
            raise DomainError(ErrorCode.NOT_FOUND, "refuted claim is elsewhere")
    key = (
        f"claim:{speaker_id.hex}:{text}:{refutes_claim_id.hex if refutes_claim_id else '-'}"
        f":{source_event_id.hex if source_event_id else uuid4().hex}"
    )
    claim = await fold_claim(
        uow,
        world_id,
        speaker_id,
        text,
        audience_location_id,
        absolute,
        refutes_claim_id,
        source_event_id,
    )
    payload: dict[str, object] = {
        "speaker_id": str(speaker_id),
        "proposition": text,
        "audience_location_id": str(audience_location_id) if audience_location_id else None,
        "refutes_claim_id": str(refutes_claim_id) if refutes_claim_id else None,
        "source_event_id": str(source_event_id) if source_event_id else None,
    }
    await uow.commands.add(
        command_id=uuid4(),
        world_id=world_id,
        key=key,
        actor_role=actor_role,
        command_type="assert_claim",
        expected_versions={},
        payload=payload,
        input_hash=canonical_input_hash({"key": key, "payload": payload}),
    )
    await uow.commit()
    return claim


async def fold_claim(
    uow: UnitOfWork,
    world_id: WorldId,
    speaker_id: CharacterId,
    text: str,
    audience_location_id: LocationId | None,
    absolute: int,
    refutes_claim_id: ClaimId | None = None,
    source_event_id: EventId | None = None,
) -> Claim:
    """Claim and belief rows without the audit command or commit.

    The API path wraps this with its command row; scene settlement
    wraps it with a settle gate. Both commit exactly once.
    """
    refuted: Claim | None = None
    if refutes_claim_id is not None:
        refuted = await uow.knowledge.get_claim(refutes_claim_id)
        if refuted.world_id != world_id:
            raise DomainError(ErrorCode.NOT_FOUND, "refuted claim is elsewhere")
    claim = Claim(
        id=new_claim_id(),
        world_id=world_id,
        speaker_id=speaker_id,
        audience_location_id=audience_location_id,
        proposition=text,
        refutes_claim_id=refutes_claim_id,
        source_event_id=source_event_id,
    )
    await uow.knowledge.add_claim(claim)
    listeners = await _eligible_listeners(uow, world_id, audience_location_id)
    for listener in listeners:
        if listener.id == speaker_id:
            confidence = SPEAKER_HOLD
        else:
            existing = await uow.knowledge.get_belief(world_id, listener.id, text)
            confidence = FIRST_HEARING if existing is None else reinforce(existing.confidence)
        await _hold_belief(uow, world_id, listener.id, text, confidence, claim.id, absolute)
        if refuted is not None:
            old = await uow.knowledge.get_belief(world_id, listener.id, refuted.proposition)
            if old is not None:
                await uow.knowledge.save_belief(
                    old.model_copy(
                        update={
                            "confidence": contradict(old.confidence),
                            "last_touched_absolute": absolute,
                        }
                    ),
                    old.version,
                )
    return claim


async def _hold_belief(
    uow: UnitOfWork,
    world_id: WorldId,
    holder_id: CharacterId,
    proposition: str,
    confidence: float,
    claim_id: ClaimId,
    absolute: int,
) -> None:
    existing = await uow.knowledge.get_belief(world_id, holder_id, proposition)
    if existing is None:
        await uow.knowledge.add_belief(
            Belief(
                id=new_belief_id(),
                world_id=world_id,
                holder_id=holder_id,
                proposition=proposition,
                confidence=confidence,
                source_claim_id=claim_id,
                last_touched_absolute=absolute,
            )
        )
        return
    await uow.knowledge.save_belief(
        existing.model_copy(
            update={
                "confidence": confidence,
                "source_claim_id": claim_id,
                "last_touched_absolute": absolute,
            }
        ),
        existing.version,
    )
