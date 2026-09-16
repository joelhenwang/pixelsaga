"""Daily summary adapter (owned by S2-SUMMARY-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.summaries import DailySummary
from worldsim.infrastructure.models.summaries import DailySummaryRow


class SqlAlchemySummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, row: DailySummaryRow) -> DailySummary:
        return DailySummary(
            id=row.id,
            world_id=row.world_id,
            owner_id=row.owner_id,
            day=row.day,
            text=row.text,
            source_ids=list(row.source_ids),
            profile_version=row.profile_version,
            prompt_version=row.prompt_version,
            fallback=row.fallback,
            version=row.version,
        )

    async def add(self, summary: DailySummary) -> None:
        self._session.add(
            DailySummaryRow(
                id=summary.id,
                world_id=summary.world_id,
                owner_id=summary.owner_id,
                day=summary.day,
                text=summary.text,
                source_ids=list(summary.source_ids),
                profile_version=summary.profile_version,
                prompt_version=summary.prompt_version,
                fallback=summary.fallback,
                version=summary.version,
            )
        )
        await self._session.flush()

    async def count_versions(self, world_id: UUID, owner_id: UUID, day: int) -> int:
        total = (
            await self._session.execute(
                select(func.count(DailySummaryRow.id)).where(
                    DailySummaryRow.world_id == world_id,
                    DailySummaryRow.owner_id == owner_id,
                    DailySummaryRow.day == day,
                )
            )
        ).scalar_one()
        return int(total)

    async def list_for_owner(self, world_id: UUID, owner_id: UUID) -> list[DailySummary]:
        rows = (
            await self._session.execute(
                select(DailySummaryRow)
                .where(
                    DailySummaryRow.world_id == world_id,
                    DailySummaryRow.owner_id == owner_id,
                )
                .order_by(DailySummaryRow.day, DailySummaryRow.version)
            )
        ).scalars()
        return [self._to_domain(row) for row in rows]
