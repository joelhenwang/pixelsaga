"""Long-term memory digest adapter (owned by S3-MEM-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.memory import MemoryDigest
from worldsim.infrastructure.models.digests import DigestRow


class SqlAlchemyDigestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, row: DigestRow) -> MemoryDigest:
        return MemoryDigest(
            id=row.id,
            world_id=row.world_id,
            owner_character_id=row.owner_character_id,
            text=row.text,
            source_ids=[str(source) for source in row.source_ids],
            day=row.day,
            created_phase_index=row.created_phase_index,
            profile_version=row.profile_version,
            prompt_version=row.prompt_version,
            version=row.version,
        )

    async def add(self, digest: MemoryDigest) -> None:
        self._session.add(
            DigestRow(
                id=digest.id,
                world_id=digest.world_id,
                owner_character_id=digest.owner_character_id,
                text=digest.text,
                source_ids=list(digest.source_ids),
                day=digest.day,
                created_phase_index=digest.created_phase_index,
                profile_version=digest.profile_version,
                prompt_version=digest.prompt_version,
                version=digest.version,
            )
        )
        await self._session.flush()

    async def count_versions(self, world_id: UUID, owner_id: UUID, day: int) -> int:
        total = (
            await self._session.execute(
                select(func.count(DigestRow.id)).where(
                    DigestRow.world_id == world_id,
                    DigestRow.owner_character_id == owner_id,
                    DigestRow.day == day,
                )
            )
        ).scalar_one()
        return int(total)

    async def list_for_owner(self, world_id: UUID, owner_id: UUID) -> list[MemoryDigest]:
        rows = (
            await self._session.execute(
                select(DigestRow)
                .where(
                    DigestRow.world_id == world_id,
                    DigestRow.owner_character_id == owner_id,
                )
                .order_by(DigestRow.day, DigestRow.version)
            )
        ).scalars()
        return [self._to_domain(row) for row in rows]
