"""Skill and inventory adapter (owned by S2-PROGRESS-001)."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.ids import ItemInstanceId
from worldsim.domain.progress import (
    CharacterSkill,
    ItemInstance,
    SkillDefinition,
    TrainingSession,
)
from worldsim.infrastructure.models.progress import (
    CharacterSkillRow,
    ItemInstanceRow,
    SkillDefinitionRow,
    TrainingSessionRow,
)
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyProgressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_skill(self, row: CharacterSkillRow) -> CharacterSkill:
        return CharacterSkill(
            id=row.id,
            world_id=row.world_id,
            character_id=row.character_id,
            skill_key=row.skill_key,
            progress=row.progress,
            sessions=row.sessions,
            version=row.version,
        )

    async def ensure_skill(
        self, world_id: UUID, skill_key: str, name: str | None = None
    ) -> SkillDefinition:
        row = (
            await self._session.execute(
                select(SkillDefinitionRow).where(
                    SkillDefinitionRow.world_id == world_id,
                    SkillDefinitionRow.key == skill_key,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            return SkillDefinition(
                id=row.id,
                world_id=row.world_id,
                key=row.key,
                name=row.name,
                max_progress=row.max_progress,
                version=row.version,
            )
        definition = SkillDefinition(
            id=uuid4(),
            world_id=world_id,
            key=skill_key,
            name=name or skill_key,
        )
        self._session.add(
            SkillDefinitionRow(
                id=definition.id,
                world_id=world_id,
                key=skill_key,
                name=definition.name,
                max_progress=definition.max_progress,
                version=0,
            )
        )
        await self._session.flush()
        return definition

    async def get_skill(
        self, world_id: UUID, character_id: UUID, skill_key: str
    ) -> CharacterSkill | None:
        row = (
            await self._session.execute(
                select(CharacterSkillRow).where(
                    CharacterSkillRow.world_id == world_id,
                    CharacterSkillRow.character_id == character_id,
                    CharacterSkillRow.skill_key == skill_key,
                )
            )
        ).scalar_one_or_none()
        return self._to_skill(row) if row is not None else None

    async def list_skills_for_character(
        self, world_id: UUID, character_id: UUID
    ) -> list[CharacterSkill]:
        rows = (
            await self._session.execute(
                select(CharacterSkillRow)
                .where(
                    CharacterSkillRow.world_id == world_id,
                    CharacterSkillRow.character_id == character_id,
                )
                .order_by(CharacterSkillRow.skill_key)
            )
        ).scalars()
        return [self._to_skill(row) for row in rows]

    async def add_skill(self, skill: CharacterSkill) -> None:
        self._session.add(
            CharacterSkillRow(
                id=skill.id,
                world_id=skill.world_id,
                character_id=skill.character_id,
                skill_key=skill.skill_key,
                progress=skill.progress,
                sessions=skill.sessions,
                version=skill.version,
            )
        )
        await self._session.flush()

    async def save_skill(self, skill: CharacterSkill, expected_version: int) -> CharacterSkill:
        row = await self._session.get(CharacterSkillRow, skill.id)
        if row is None:
            raise missing("character skill", skill.id)
        if row.version != expected_version:
            raise version_conflict("character skill", skill.id, expected_version, row.version)
        row.progress = skill.progress
        row.sessions = skill.sessions
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_skill(row)

    async def has_session(
        self, world_id: UUID, character_id: UUID, skill_key: str, session_key: str
    ) -> bool:
        row = (
            await self._session.execute(
                select(TrainingSessionRow.id).where(
                    TrainingSessionRow.world_id == world_id,
                    TrainingSessionRow.character_id == character_id,
                    TrainingSessionRow.skill_key == skill_key,
                    TrainingSessionRow.session_key == session_key,
                )
            )
        ).scalar_one_or_none()
        return row is not None

    async def add_session(self, session: TrainingSession) -> None:
        self._session.add(
            TrainingSessionRow(
                id=session.id,
                world_id=session.world_id,
                character_id=session.character_id,
                skill_key=session.skill_key,
                session_key=session.session_key,
                gain=session.gain,
                version=session.version,
            )
        )
        await self._session.flush()


class SqlAlchemyInventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_item(self, row: ItemInstanceRow) -> ItemInstance:
        return ItemInstance(
            id=row.id,
            world_id=row.world_id,
            item_key=row.item_key,
            owner_id=row.owner_id,
            quantity=row.quantity,
            version=row.version,
        )

    async def get_item(self, item_id: ItemInstanceId) -> ItemInstance:
        row = await self._session.get(ItemInstanceRow, item_id)
        if row is None:
            raise missing("item instance", item_id)
        return self._to_item(row)

    async def list_for_owner(self, world_id: UUID, owner_id: UUID | None) -> list[ItemInstance]:
        rows = (
            await self._session.execute(
                select(ItemInstanceRow)
                .where(
                    ItemInstanceRow.world_id == world_id,
                    ItemInstanceRow.owner_id == owner_id,
                )
                .order_by(ItemInstanceRow.item_key)
            )
        ).scalars()
        return [self._to_item(row) for row in rows]

    async def add_item(self, item: ItemInstance) -> None:
        self._session.add(
            ItemInstanceRow(
                id=item.id,
                world_id=item.world_id,
                item_key=item.item_key,
                owner_id=item.owner_id,
                quantity=item.quantity,
                version=item.version,
            )
        )
        await self._session.flush()

    async def save_item(self, item: ItemInstance, expected_version: int) -> ItemInstance:
        row = await self._session.get(ItemInstanceRow, item.id)
        if row is None:
            raise missing("item instance", item.id)
        if row.version != expected_version:
            raise version_conflict("item instance", item.id, expected_version, row.version)
        row.owner_id = item.owner_id
        row.quantity = item.quantity
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_item(row)

    async def remove_item(self, item_id: ItemInstanceId) -> None:
        row = await self._session.get(ItemInstanceRow, item_id)
        if row is None:
            raise missing("item instance", item_id)
        await self._session.delete(row)
        await self._session.flush()
