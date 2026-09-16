"""Relationship evidence commands (owned by S2-REL-001).

Recording validates both endpoints, clamps the fold, and lands the
evidence, the folded projection, and the audit command in one
transaction. Scene replays pass their event ID so the same evidence
never records twice; adhoc calls mint a fresh key per call.
"""

from __future__ import annotations

from uuid import uuid4

from worldsim.application.transactions.canonical import canonical_input_hash
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.enums import LifeStatus, RelationshipDimension
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    CharacterId,
    EventId,
    WorldId,
    new_relationship_evidence_id,
    new_relationship_id,
)
from worldsim.domain.relationships import (
    Relationship,
    RelationshipEvidence,
    fold,
)


async def record_evidence(
    uow: UnitOfWork,
    actor_role: str,
    world_id: WorldId,
    source_id: CharacterId,
    target_id: CharacterId,
    dimension: RelationshipDimension,
    delta: int,
    note: str = "",
    source_event_id: EventId | None = None,
) -> Relationship:
    """Fold one directional evidence delta into the projection."""
    if source_id == target_id:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "no self-directed evidence")
    source = await uow.characters.get(source_id)
    target = await uow.characters.get(target_id)
    if source.world_id != world_id or target.world_id != world_id:
        raise DomainError(ErrorCode.NOT_FOUND, "both ends live in this world")
    if source.life_status != LifeStatus.ALIVE:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, "the dead leave no evidence")
    key = (
        f"rel:{source_id.hex}:{target_id.hex}:{dimension.value}:{delta}"
        f":{source_event_id.hex if source_event_id else uuid4().hex}"
    )
    payload: dict[str, object] = {
        "source_id": str(source_id),
        "target_id": str(target_id),
        "dimension": dimension.value,
        "delta": delta,
        "note": note,
        "source_event_id": str(source_event_id) if source_event_id else None,
    }
    await uow.commands.add(
        command_id=uuid4(),
        world_id=world_id,
        key=key,
        actor_role=actor_role,
        command_type="record_relationship_evidence",
        expected_versions={},
        payload=payload,
        input_hash=canonical_input_hash({"key": key, "payload": payload}),
    )
    evidence = RelationshipEvidence(
        id=new_relationship_evidence_id(),
        world_id=world_id,
        source_id=source_id,
        target_id=target_id,
        dimension=dimension,
        delta=delta,
        note=note,
        source_event_id=source_event_id,
    )
    await uow.relationships.add_evidence(evidence)
    current = await uow.relationships.get_pair(world_id, source_id, target_id)
    if current is None:
        current = Relationship(
            id=new_relationship_id(),
            world_id=world_id,
            source_id=source_id,
            target_id=target_id,
        )
        await uow.relationships.add_relationship(current)
    folded = fold(evidence, current)
    saved = await uow.relationships.save_relationship(folded, current.version)
    await uow.commit()
    return saved
