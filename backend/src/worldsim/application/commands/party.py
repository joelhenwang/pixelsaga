"""Party commands: begin adventure and recruit companions (owned by DND-WIRE).

Joins are inserts guarded by the party cap; repeat RECRUIT tags for a
name already present return the existing member without writing, which
is what makes the monolith's streaming-tolerant scan safe to replay.
"""

from __future__ import annotations

from dataclasses import dataclass

from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.activities import focus_for_seat
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.enums import LifeStatus
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    CharacterId,
    LocationId,
    PartyMemberId,
    WorldId,
    new_card_id,
    new_character_id,
    new_party_member_id,
)
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
    character_id: CharacterId | None = None,
) -> PartyMember:
    """Seat the player's adventurer: explicit stats or the auto build."""
    await _check_cap(uow, world_id)

    if character_id is not None:
        character = await uow.characters.get(character_id)
        if character.world_id != world_id:
            raise DomainError(ErrorCode.NOT_FOUND, "character is not in this world")

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
        character_id=character_id,
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


async def create_character(
    uow: UnitOfWork,
    world_id: WorldId,
    name: str,
    location_id: LocationId,
    appearance: str = "",
    personality: str = "",
    background: str = "",
) -> Character:
    """Create a simulation character with its identity card, atomically."""
    location = await uow.locations.get(location_id)
    if location.world_id != world_id:
        raise DomainError(ErrorCode.NOT_FOUND, "location is not in this world")
    character_id = new_character_id()
    character = Character(
        id=character_id,
        world_id=world_id,
        name=name,
        card_version=1,
        life_status=LifeStatus.ALIVE,
        location_id=location_id,
        stamina=80,
        mana=50,
        conditions=[],
    )
    card = CharacterCard(
        id=new_card_id(),
        character_id=character_id,
        name=name,
        appearance=appearance,
        personality=personality,
        background=background,
    )
    await uow.characters.add_identity(character_id, world_id, name)
    await uow.characters.add_state(character)
    await uow.characters.add_card(card)
    await uow.commit()
    return character


async def link_member(
    uow: UnitOfWork,
    world_id: WorldId,
    member_id: PartyMemberId,
    character_id: CharacterId,
    expected_version: int,
) -> PartyMember:
    """Bind an existing roster row to a real character, version-checked."""
    member = await uow.party.get(member_id)
    if member.world_id != world_id:
        raise DomainError(ErrorCode.NOT_FOUND, "party member is not in this world")
    character = await uow.characters.get(character_id)
    if character.world_id != world_id:
        raise DomainError(ErrorCode.NOT_FOUND, "character is not in this world")
    if member.character_id is not None and member.character_id != character_id:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, "party member is already linked elsewhere")
    linked = await uow.party.save_link(member_id, character_id, expected_version)
    await uow.commit()
    return linked
