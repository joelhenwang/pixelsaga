"""D&D monster pool adapter (owned by DND-MONSTER)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.ids import MonsterId
from worldsim.domain.party import Monster
from worldsim.infrastructure.models.monsters import MonsterRow
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyMonsterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, row: MonsterRow) -> Monster:
        return Monster(
            id=row.id,
            world_id=row.world_id,
            name_key=row.name_key,
            name=row.name,
            hp_current=row.hp_current,
            hp_max=row.hp_max,
            ac=row.ac,
            version=row.version,
        )

    async def list_for_world(self, world_id: UUID) -> list[Monster]:
        rows = (
            await self._session.execute(
                select(MonsterRow).where(MonsterRow.world_id == world_id).order_by(MonsterRow.name)
            )
        ).scalars()
        return [self._to_domain(row) for row in rows]

    async def add(self, monster: Monster) -> None:
        self._session.add(
            MonsterRow(
                id=monster.id,
                world_id=monster.world_id,
                name_key=monster.name_key,
                name=monster.name,
                hp_current=monster.hp_current,
                hp_max=monster.hp_max,
                ac=monster.ac,
                version=monster.version,
            )
        )
        await self._session.flush()

    async def save_hp(
        self, monster_id: MonsterId, hp_current: int, expected_version: int
    ) -> Monster:
        row = await self._session.get(MonsterRow, monster_id)
        if row is None:
            raise missing("monster", monster_id)
        if row.version != expected_version:
            raise version_conflict("monster", monster_id, expected_version, row.version)
        row.hp_current = hp_current
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_domain(row)
