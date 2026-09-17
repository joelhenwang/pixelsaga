"""Birth, death, and focus succession (owned by S5-GENEALOGY-001).

Schedule consequences run inside the engine's fire transaction, so
consequence rows commit atomically with the schedule-fired event that
is their provenance. Birth identity derives from the schedule ID:
re-firing an applied schedule is impossible, and a duplicate birth
schedule for the same row is a visible skip, never a second child.

The engine never assigns focus. Only ``assign_focus`` writes focus
rows, gated on succession eligibility for recorded characters;
founders carry no lineage record and pass the gate. Descendants start
with no memories: nothing here reads or writes perception records.
"""

from __future__ import annotations

from uuid import UUID

from worldsim.application.transactions.canonical import UnitOfWorkFactory
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.enums import FocusSlot, LifeStatus
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    derive_lineage_child_id,
    new_card_id,
    new_focus_assignment_id,
    new_lineage_link_id,
)
from worldsim.domain.macro import FocusAssignment, LineageCharacter, LineageLink
from worldsim.domain.schedules import ScheduledEffect

BIRTH_KIND = "birth"
DEATH_KIND = "death"


def age_phases(record: LineageCharacter, at_absolute: int) -> int:
    return max(0, at_absolute - record.birth_absolute)


async def apply_schedule_consequence(uow: UnitOfWork, schedule: ScheduledEffect) -> None:
    if schedule.kind == BIRTH_KIND:
        await _apply_birth(uow, schedule)
    elif schedule.kind == DEATH_KIND:
        await _apply_death(uow, schedule)


async def _apply_birth(uow: UnitOfWork, schedule: ScheduledEffect) -> None:
    payload = schedule.payload
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise DomainError(ErrorCode.VALIDATION_FAILED, "birth schedule needs a name")
    child_id = derive_lineage_child_id(schedule.id)
    try:
        await uow.characters.get(child_id)
        return
    except DomainError:
        pass
    parent_ids = [UUID(str(raw)) for raw in payload.get("parent_ids", [])]
    if "location_id" in payload:
        location_id = UUID(str(payload["location_id"]))
    elif parent_ids:
        location_id = (await uow.characters.get(parent_ids[0])).location_id
    else:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "birth schedule needs a location")
    world_id = schedule.world_id
    await uow.characters.add_identity(child_id, world_id, name.strip())
    await uow.characters.add_card(
        CharacterCard(
            id=new_card_id(),
            character_id=child_id,
            name=name.strip(),
            appearance=str(payload.get("appearance", "")),
            personality=str(payload.get("personality", "")),
            background=str(payload.get("background", "")),
        )
    )
    await uow.characters.add_state(
        Character(
            id=child_id,
            world_id=world_id,
            name=name.strip(),
            card_version=1,
            location_id=location_id,
            stamina=int(payload.get("stamina", 100)),
            mana=int(payload.get("mana", 100)),
        )
    )
    await uow.versions.ensure(child_id, world_id, "character")
    for parent_id in parent_ids:
        await uow.lineage.add_link(
            LineageLink(
                id=new_lineage_link_id(),
                world_id=world_id,
                parent_id=parent_id,
                child_id=child_id,
                birth_absolute=schedule.due_absolute,
            )
        )
    await uow.lineage.put_record(
        LineageCharacter(
            character_id=child_id,
            world_id=world_id,
            birth_absolute=schedule.due_absolute,
            succession_eligible=payload.get("succession_eligible", False) is True,
        )
    )


async def _apply_death(uow: UnitOfWork, schedule: ScheduledEffect) -> None:
    raw = schedule.payload.get("character_id")
    if not isinstance(raw, str):
        raise DomainError(ErrorCode.VALIDATION_FAILED, "death schedule needs a character_id")
    character_id = UUID(raw)
    try:
        record = await uow.lineage.get_record(character_id)
    except DomainError:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, "death needs a recorded lineage character"
        ) from None
    character = await uow.characters.get(character_id)
    if character.life_status == LifeStatus.DEAD:
        return
    await uow.characters.save_state(
        character.model_copy(update={"life_status": LifeStatus.DEAD}), character.version
    )
    await uow.lineage.put_record(
        record.model_copy(
            update={
                "death_absolute": schedule.due_absolute,
                "life_status": LifeStatus.DEAD,
            }
        )
    )


async def current_focus(
    factory: UnitOfWorkFactory, world_id: UUID, slot: FocusSlot
) -> FocusAssignment | None:
    async with factory() as uow:
        assignments = await uow.lineage.list_focus(world_id, slot)
        return assignments[0] if assignments else None


async def assign_focus(
    factory: UnitOfWorkFactory,
    world_id: UUID,
    slot: FocusSlot,
    to_character_id: UUID,
    reason: str,
    effective_absolute: int,
    *,
    from_character_id: UUID | None = None,
) -> FocusAssignment:
    async with factory() as uow:
        try:
            record = await uow.lineage.get_record(to_character_id)
        except DomainError:
            record = None
        if record is not None and slot != FocusSlot.COMPANION and not record.succession_eligible:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "recorded characters need succession eligibility for focus slots",
            )
        holder = from_character_id
        if holder is None:
            current = await uow.lineage.list_focus(world_id, slot)
            holder = current[0].to_character_id if current else None
        version = len(await uow.lineage.list_focus(world_id, slot))
        assignment = FocusAssignment(
            id=new_focus_assignment_id(),
            world_id=world_id,
            slot=slot,
            from_character_id=holder,
            to_character_id=to_character_id,
            effective_absolute=effective_absolute,
            reason=reason,
            version=version,
        )
        await uow.lineage.add_focus(assignment)
        await uow.commit()
        return assignment
