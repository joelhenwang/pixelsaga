"""Persistent world-condition lifecycle (owned by REVAMP-P09).

Creation comes from the intervention queue; ticks run at phase
boundaries through canonical commits, so consequences are versioned,
audited events rather than silent stat edits. Recovery and expiry are
deterministic functions of the phase index.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from worldsim.application.transactions.canonical import (
    CanonicalTransaction,
    CommitRequest,
    canonical_input_hash,
)
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.characters import Character
from worldsim.domain.conditions import ConditionStatus, ConditionType, WorldCondition
from worldsim.domain.effects import DomainEffect, ResourceAdjustedEffect
from worldsim.domain.enums import EventType, LifeStatus, ResourceKind
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import LocationId, WorldId, new_world_condition_id


async def create_condition(
    uow: UnitOfWork,
    world_id: WorldId,
    kind: ConditionType,
    label: str,
    detail: str,
    location_ids: list[LocationId],
    severity: int,
    starts_absolute: int,
    ends_absolute: int,
    source_intervention_id: UUID | None = None,
) -> WorldCondition:
    """Persist a bounded condition after validating scope and window."""
    if not location_ids:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "conditions need a scope")
    if ends_absolute <= starts_absolute:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "conditions end after they start")
    locations = {loc.id for loc in await uow.locations.list_for_world(world_id)}
    unknown = [loc for loc in location_ids if loc not in locations]
    if unknown:
        raise DomainError(ErrorCode.NOT_FOUND, "condition scope is not in this world")
    condition = WorldCondition(
        id=new_world_condition_id(),
        world_id=world_id,
        kind=kind,
        public_label=label,
        detail=detail,
        scope_location_ids=list(location_ids),
        severity=severity,
        started_absolute=starts_absolute,
        ends_absolute=ends_absolute,
        source_intervention_id=source_intervention_id,
    )
    await uow.conditions.add_condition(condition)
    await uow.commit()
    return condition


async def tick_conditions(
    factory: Callable[[], UnitOfWork], world_id: WorldId, index: int
) -> list[UUID]:
    """Apply due condition ticks for one boundary; returns tick event ids."""
    async with factory() as uow:
        conditions = await uow.conditions.list_active_for_world(world_id)
        characters = await uow.characters.list_for_world(world_id)
    ticked: list[UUID] = []
    for condition in conditions:
        if index < condition.started_absolute:
            continue
        if index > condition.ends_absolute:
            await _recover(factory, condition)
            continue
        event_id = await _tick_illness(factory, world_id, index, condition, characters)
        if event_id is not None:
            ticked.append(event_id)
    return ticked


async def _recover(factory: Callable[[], UnitOfWork], condition: WorldCondition) -> None:
    async with factory() as uow:
        current = await uow.conditions.get_condition(condition.id)
        if current.status != ConditionStatus.ACTIVE:
            return
        await uow.conditions.save_condition(
            current.model_copy(update={"status": ConditionStatus.RECOVERED}), current.version
        )
        await uow.commit()


async def _tick_illness(
    factory: Callable[[], UnitOfWork],
    world_id: WorldId,
    index: int,
    condition: WorldCondition,
    characters: list[Character],
) -> UUID | None:
    scope = set(condition.scope_location_ids)
    victims = [
        c
        for c in characters
        if c.location_id in scope and c.life_status == LifeStatus.ALIVE and c.stamina > 0
    ]
    if not victims:
        return None
    effects: list[DomainEffect] = [
        ResourceAdjustedEffect(
            affected_ids=[victim.id],
            expected_versions={str(victim.id): victim.version},
            resource=ResourceKind.STAMINA,
            delta=-min(condition.severity, victim.stamina),
        )
        for victim in victims
    ]
    key = f"condition:{condition.id.hex}:{index}"
    result = await CanonicalTransaction(factory).commit(
        CommitRequest(
            command_id=uuid4(),
            world_id=world_id,
            idempotency_key=key,
            actor_role="system",
            command_type="condition_tick",
            expected_versions={str(v.id): v.version for v in victims},
            payload={"condition_id": str(condition.id), "label": condition.public_label},
            input_hash=canonical_input_hash({"key": key}),
            absolute_index=index,
            phase_run_id=None,
            event_type=EventType.CONDITION_TICK,
            effects=effects,
        )
    )
    return result.event_id


async def active_conditions(
    factory: Callable[[], UnitOfWork], world_id: WorldId
) -> list[WorldCondition]:
    """Active conditions for macro gating and operator display."""
    async with factory() as uow:
        return await uow.conditions.list_active_for_world(world_id)
