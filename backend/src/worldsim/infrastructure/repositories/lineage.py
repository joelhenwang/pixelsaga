"""Genealogy persistence adapter (owned by S5-GENEALOGY-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.enums import FocusSlot, LifeStatus
from worldsim.domain.macro import FocusAssignment, LineageCharacter, LineageLink
from worldsim.infrastructure.models.macro import (
    FocusAssignmentRow,
    LineageCharacterRow,
    LineageLinkRow,
)
from worldsim.infrastructure.repositories._common import missing


class SqlAlchemyLineageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_link(self, row: LineageLinkRow) -> LineageLink:
        return LineageLink(
            id=row.id,
            world_id=row.world_id,
            parent_id=row.parent_id,
            child_id=row.child_id,
            birth_absolute=row.birth_absolute,
        )

    def _to_record(self, row: LineageCharacterRow) -> LineageCharacter:
        return LineageCharacter(
            character_id=row.character_id,
            world_id=row.world_id,
            birth_absolute=row.birth_absolute,
            death_absolute=row.death_absolute,
            life_status=LifeStatus(row.life_status),
            succession_eligible=row.succession_eligible,
        )

    def _to_focus(self, row: FocusAssignmentRow) -> FocusAssignment:
        return FocusAssignment(
            id=row.id,
            world_id=row.world_id,
            slot=FocusSlot(row.slot),
            from_character_id=row.from_character_id,
            to_character_id=row.to_character_id,
            effective_absolute=row.effective_absolute,
            reason=row.reason,
            version=row.version,
        )

    async def add_link(self, link: LineageLink) -> None:
        self._session.add(
            LineageLinkRow(
                id=link.id,
                world_id=link.world_id,
                parent_id=link.parent_id,
                child_id=link.child_id,
                birth_absolute=link.birth_absolute,
            )
        )
        await self._session.flush()

    async def list_children(self, world_id: UUID, parent_id: UUID) -> list[LineageLink]:
        rows = (
            await self._session.execute(
                select(LineageLinkRow)
                .where(
                    LineageLinkRow.world_id == world_id,
                    LineageLinkRow.parent_id == parent_id,
                )
                .order_by(LineageLinkRow.birth_absolute)
            )
        ).scalars()
        return [self._to_link(row) for row in rows]

    async def list_parents(self, world_id: UUID, child_id: UUID) -> list[LineageLink]:
        rows = (
            await self._session.execute(
                select(LineageLinkRow)
                .where(
                    LineageLinkRow.world_id == world_id,
                    LineageLinkRow.child_id == child_id,
                )
                .order_by(LineageLinkRow.birth_absolute)
            )
        ).scalars()
        return [self._to_link(row) for row in rows]

    async def get_record(self, character_id: UUID) -> LineageCharacter:
        row = await self._session.get(LineageCharacterRow, character_id)
        if row is None:
            raise missing("lineage character", character_id)
        return self._to_record(row)

    async def put_record(self, record: LineageCharacter) -> None:
        row = await self._session.get(LineageCharacterRow, record.character_id)
        if row is None:
            self._session.add(
                LineageCharacterRow(
                    character_id=record.character_id,
                    world_id=record.world_id,
                    birth_absolute=record.birth_absolute,
                    death_absolute=record.death_absolute,
                    life_status=record.life_status.value,
                    succession_eligible=record.succession_eligible,
                )
            )
        else:
            row.birth_absolute = record.birth_absolute
            row.death_absolute = record.death_absolute
            row.life_status = record.life_status.value
            row.succession_eligible = record.succession_eligible
        await self._session.flush()

    async def add_focus(self, assignment: FocusAssignment) -> None:
        self._session.add(
            FocusAssignmentRow(
                id=assignment.id,
                world_id=assignment.world_id,
                slot=assignment.slot.value,
                from_character_id=assignment.from_character_id,
                to_character_id=assignment.to_character_id,
                effective_absolute=assignment.effective_absolute,
                reason=assignment.reason,
                version=assignment.version,
            )
        )
        await self._session.flush()

    async def list_focus(self, world_id: UUID, slot: FocusSlot) -> list[FocusAssignment]:
        rows = (
            await self._session.execute(
                select(FocusAssignmentRow)
                .where(
                    FocusAssignmentRow.world_id == world_id,
                    FocusAssignmentRow.slot == slot.value,
                )
                .order_by(FocusAssignmentRow.effective_absolute.desc())
            )
        ).scalars()
        return [self._to_focus(row) for row in rows]

    async def list_deaths(
        self, world_id: UUID, start_absolute: int, end_absolute: int
    ) -> list[LineageCharacter]:
        rows = (
            await self._session.execute(
                select(LineageCharacterRow)
                .where(
                    LineageCharacterRow.world_id == world_id,
                    LineageCharacterRow.death_absolute.is_not(None),
                    LineageCharacterRow.death_absolute >= start_absolute,
                    LineageCharacterRow.death_absolute < end_absolute,
                )
                .order_by(LineageCharacterRow.death_absolute)
            )
        ).scalars()
        return [self._to_record(row) for row in rows]
