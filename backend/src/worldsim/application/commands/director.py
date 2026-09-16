"""Director acceptance shared by graph and user paths (owned by S2-ROLE-001)."""

from __future__ import annotations

from uuid import uuid4

from worldsim.application.transactions.canonical import canonical_input_hash
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.director import DirectorDecision
from worldsim.domain.ids import WorldId


async def accept_decision(
    uow: UnitOfWork,
    world_id: WorldId,
    decision: DirectorDecision,
    actor_role: str,
    key: str,
    last_absolute: int,
) -> None:
    """Persist accepted rows, audit the command, and advance the cooldown."""
    await uow.worlds.put_config(world_id, "director.last_absolute", last_absolute)
    if decision.accepted:
        if decision.hook is not None:
            await uow.narrative.add_hook(decision.hook)
        if decision.arc is not None:
            await uow.narrative.add_arc(decision.arc)
        payload: dict[str, object] = {
            "hook_id": str(decision.hook.id) if decision.hook else None,
            "arc_id": str(decision.arc.id) if decision.arc else None,
        }
        await uow.commands.add(
            command_id=uuid4(),
            world_id=world_id,
            key=key,
            actor_role=actor_role,
            command_type="director_proposal",
            expected_versions={},
            payload=payload,
            input_hash=canonical_input_hash({"key": key, "payload": payload}),
        )
    await uow.commit()
