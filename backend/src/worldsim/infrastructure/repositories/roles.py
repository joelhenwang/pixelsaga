"""Role grant adapter (owned by S2-ROLE-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.enums import UserRole
from worldsim.domain.roles import RoleGrant
from worldsim.infrastructure.models.roles import RoleGrantRow


class SqlAlchemyRoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, row: RoleGrantRow) -> RoleGrant:
        return RoleGrant(
            id=row.id,
            world_id=row.world_id,
            role=UserRole(row.role),
            character_id=row.character_id,
            granted_absolute=row.granted_absolute,
            version=row.version,
        )

    async def get_for_world(self, world_id: UUID) -> RoleGrant | None:
        row = (
            await self._session.execute(
                select(RoleGrantRow).where(RoleGrantRow.world_id == world_id)
            )
        ).scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    async def set_grant(self, grant: RoleGrant) -> RoleGrant:
        existing = (
            await self._session.execute(
                select(RoleGrantRow).where(RoleGrantRow.world_id == grant.world_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            self._session.add(
                RoleGrantRow(
                    id=grant.id,
                    world_id=grant.world_id,
                    role=grant.role.value,
                    character_id=grant.character_id,
                    granted_absolute=grant.granted_absolute,
                    version=grant.version,
                )
            )
        else:
            existing.role = grant.role.value
            existing.character_id = grant.character_id
            existing.granted_absolute = grant.granted_absolute
            existing.version = existing.version + 1
        await self._session.flush()
        stored = (
            await self._session.execute(
                select(RoleGrantRow).where(RoleGrantRow.world_id == grant.world_id)
            )
        ).scalar_one()
        return self._to_domain(stored)
