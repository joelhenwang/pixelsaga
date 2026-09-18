"""D&D party roster adapter (owned by DND-WIRE)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.enums import FocusSlot
from worldsim.domain.ids import PartyMemberId
from worldsim.domain.party import PartyMember
from worldsim.domain.rules.dnd import Sheet
from worldsim.infrastructure.models.party import PartyMemberRow
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyPartyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, row: PartyMemberRow) -> PartyMember:
        return PartyMember(
            id=row.id,
            world_id=row.world_id,
            name=row.name,
            name_key=row.name_key,
            character_id=row.character_id,
            focus_slot=FocusSlot(row.focus_slot),
            sheet=Sheet.model_validate(row.sheet),
            version=row.version,
        )

    async def get(self, member_id: PartyMemberId) -> PartyMember:
        row = await self._session.get(PartyMemberRow, member_id)
        if row is None:
            raise missing("party member", member_id)
        return self._to_domain(row)

    async def list_for_world(self, world_id: UUID) -> list[PartyMember]:
        rows = (
            await self._session.execute(
                select(PartyMemberRow)
                .where(PartyMemberRow.world_id == world_id)
                .order_by(PartyMemberRow.name)
            )
        ).scalars()
        return [self._to_domain(row) for row in rows]

    async def find_by_name(self, world_id: UUID, name_key: str) -> PartyMember | None:
        row = (
            await self._session.execute(
                select(PartyMemberRow).where(
                    PartyMemberRow.world_id == world_id,
                    PartyMemberRow.name_key == name_key,
                )
            )
        ).scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    async def add(self, member: PartyMember) -> None:
        self._session.add(
            PartyMemberRow(
                id=member.id,
                world_id=member.world_id,
                name_key=member.name_key,
                name=member.name,
                character_id=member.character_id,
                focus_slot=member.focus_slot.value,
                sheet=member.sheet.model_dump(),
                version=member.version,
            )
        )
        await self._session.flush()

    async def save_sheet(
        self, member_id: PartyMemberId, sheet: Sheet, expected_version: int
    ) -> PartyMember:
        row = await self._session.get(PartyMemberRow, member_id)
        if row is None:
            raise missing("party member", member_id)
        if row.version != expected_version:
            raise version_conflict("party member", member_id, expected_version, row.version)
        row.sheet = sheet.model_dump()
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_domain(row)

    async def save_link(
        self, member_id: PartyMemberId, character_id: UUID, expected_version: int
    ) -> PartyMember:
        row = await self._session.get(PartyMemberRow, member_id)
        if row is None:
            raise missing("party member", member_id)
        if row.version != expected_version:
            raise version_conflict("party member", member_id, expected_version, row.version)
        row.character_id = character_id
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_domain(row)
