"""Typed deity overrides (owned by S2-ROLE-001).

One canonical commit applies an explicit character patch; unset
fields stay untouched. Retcon overrides additionally enqueue a
consistency-audit message and mark the event summary, so history
preserves the rewrite and its consequences stay traceable.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from worldsim.application.transactions.canonical import (
    CanonicalTransaction,
    CommitRequest,
    OutboxSpec,
    canonical_input_hash,
)
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.effects import DeityOverrideEffect
from worldsim.domain.enums import EventType, LifeStatus
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import CharacterId, PhaseRunId, WorldId


async def apply_override(
    factory: Callable[[], UnitOfWork],
    world_id: WorldId,
    character_id: CharacterId,
    run_id: PhaseRunId,
    absolute: int,
    stamina: int | None = None,
    mana: int | None = None,
    life_status: LifeStatus | None = None,
    conditions: list[str] | None = None,
    retcon: bool = False,
) -> UUID:
    """Patch one character through a deity commit; returns the event ID."""
    if all(value is None for value in (stamina, mana, life_status, conditions)):
        raise DomainError(ErrorCode.VALIDATION_FAILED, "overrides change something")
    async with factory() as uow:
        character = await uow.characters.get(character_id)
    if character.world_id != world_id:
        raise DomainError(ErrorCode.NOT_FOUND, "character is not in this world")
    effect = DeityOverrideEffect(
        affected_ids=[character_id],
        expected_versions={str(character_id): character.version},
        character_id=character_id,
        stamina=stamina,
        mana=mana,
        life_status=life_status,
        conditions=conditions,
        retcon=retcon,
    )
    key = f"deity:{character_id.hex}:{uuid4().hex}"
    outbox = (
        [
            OutboxSpec(
                kind="consistency_audit",
                payload={"character_id": str(character_id), "retcon": True},
                key=f"{key}:audit",
            )
        ]
        if retcon
        else []
    )
    result = await CanonicalTransaction(factory).commit(
        CommitRequest(
            command_id=uuid4(),
            world_id=world_id,
            idempotency_key=key,
            actor_role="deity",
            command_type="deity_override",
            expected_versions={str(character_id): character.version},
            payload={
                "character_id": str(character_id),
                "stamina": stamina,
                "mana": mana,
                "life_status": life_status.value if life_status else None,
                "conditions": conditions,
                "retcon": retcon,
            },
            input_hash=canonical_input_hash({"key": key}),
            absolute_index=absolute,
            phase_run_id=run_id,
            event_type=EventType.DEITY_OVERRIDE,
            effects=[effect],
            outbox=outbox,
        )
    )
    return result.event_id
