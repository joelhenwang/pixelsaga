"""Party commands: begin adventure and recruit companions (owned by DND-WIRE).

Joins are inserts guarded by the party cap; repeat RECRUIT tags for a
name already present return the existing member without writing, which
is what makes the monolith's streaming-tolerant scan safe to replay.
"""

from __future__ import annotations

from dataclasses import dataclass

from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.activities import focus_for_seat
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import WorldId, new_party_member_id
from worldsim.domain.party import PartyMember, party_name_key
from worldsim.domain.rules.dnd import (
    MAX_PARTY_SIZE,
    DataTables,
    Sheet,
    auto_sheet,
    recruit_sheet,
)
from worldsim.domain.rules.dnd.sheets import ensure_hp, max_hp


@dataclass(frozen=True)
class RecruitResult:
    member: PartyMember
    joined: bool


async def _check_cap(uow: UnitOfWork, world_id: WorldId) -> None:
    roster = await uow.party.list_for_world(world_id)
    if len(roster) >= MAX_PARTY_SIZE:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            f"party is full ({MAX_PARTY_SIZE} adventurers max)",
            {"world_id": str(world_id)},
        )


async def begin_adventure(
    uow: UnitOfWork,
    data: DataTables,
    world_id: WorldId,
    name: str,
    race: str,
    class_key: str,
    level: int,
    stats: dict[str, int] | None = None,
) -> PartyMember:
    """Seat the player's adventurer: explicit stats or the auto build."""
    await _check_cap(uow, world_id)

    key = party_name_key(name)
    existing = await uow.party.find_by_name(world_id, key)
    if existing is not None:
        return existing
    if stats is None:
        sheet = auto_sheet(name, race, class_key, level, data)
    else:
        sheet = Sheet(name=name, race=race, character_class=class_key, level=level, stats=stats)
        ensure_hp(sheet, max_hp(data, sheet))
    seated = len(await uow.party.list_for_world(world_id))
    member = PartyMember(
        id=new_party_member_id(),
        world_id=world_id,
        name=name,
        name_key=key,
        focus_slot=focus_for_seat(seated),
        sheet=sheet,
    )
    await uow.party.add(member)
    await uow.commit()
    return member


async def recruit_companion(
    uow: UnitOfWork,
    data: DataTables,
    world_id: WorldId,
    tag_name: str,
    desc: str,
) -> RecruitResult:
    """Resolve one RECRUIT tag; replays for known names are no-ops."""
    key = party_name_key(tag_name)
    existing = await uow.party.find_by_name(world_id, key)
    if existing is not None:
        return RecruitResult(member=existing, joined=False)
    await _check_cap(uow, world_id)
    roster = await uow.party.list_for_world(world_id)
    sheet = recruit_sheet(tag_name, desc, [m.sheet.level for m in roster] or [1], data)
    member = PartyMember(
        id=new_party_member_id(),
        world_id=world_id,
        name=tag_name.strip(),
        name_key=key,
        focus_slot=focus_for_seat(len(roster)),
        sheet=sheet,
    )
    await uow.party.add(member)
    await uow.commit()
    return RecruitResult(member=member, joined=True)
