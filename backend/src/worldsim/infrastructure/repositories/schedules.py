"""Scheduled-effect adapter (owned by S2-TIME-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.enums import ScheduleStatus
from worldsim.domain.schedules import ScheduledEffect
from worldsim.infrastructure.models.schedules import ScheduledEffectRow
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyScheduleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, row: ScheduledEffectRow) -> ScheduledEffect:
        return ScheduledEffect(
            id=row.id,
            world_id=row.world_id,
            due_absolute=row.due_absolute,
            kind=row.kind,
            payload=dict(row.payload),
            status=ScheduleStatus(row.status),
            version=row.version,
        )

    async def add(self, schedule: ScheduledEffect) -> None:
        self._session.add(
            ScheduledEffectRow(
                id=schedule.id,
                world_id=schedule.world_id,
                due_absolute=schedule.due_absolute,
                kind=schedule.kind,
                payload=dict(schedule.payload),
                status=schedule.status.value,
                version=schedule.version,
            )
        )
        await self._session.flush()

    async def get(self, schedule_id: UUID) -> ScheduledEffect:
        row = await self._session.get(ScheduledEffectRow, schedule_id)
        if row is None:
            raise missing("scheduled effect", schedule_id)
        return self._to_domain(row)

    async def list_due(self, world_id: UUID, absolute: int) -> list[ScheduledEffect]:
        rows = (
            await self._session.execute(
                select(ScheduledEffectRow)
                .where(
                    ScheduledEffectRow.world_id == world_id,
                    ScheduledEffectRow.due_absolute <= absolute,
                    ScheduledEffectRow.status == ScheduleStatus.PENDING.value,
                )
                .order_by(ScheduledEffectRow.due_absolute)
            )
        ).scalars()
        return [self._to_domain(row) for row in rows]

    async def save(self, schedule: ScheduledEffect, expected_version: int) -> ScheduledEffect:
        row = await self._session.get(ScheduledEffectRow, schedule.id)
        if row is None:
            raise missing("scheduled effect", schedule.id)
        if row.version != expected_version:
            raise version_conflict("scheduled effect", schedule.id, expected_version, row.version)
        row.status = schedule.status.value
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_domain(row)
