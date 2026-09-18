"""World condition adapter (owned by REVAMP-P09)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.conditions import ConditionStatus, ConditionType, WorldCondition
from worldsim.domain.ids import WorldConditionId
from worldsim.infrastructure.models.conditions import WorldConditionRow
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyConditionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, row: WorldConditionRow) -> WorldCondition:
        return WorldCondition(
            id=row.id,
            world_id=row.world_id,
            kind=ConditionType(row.kind),
            public_label=row.public_label,
            detail=row.detail,
            scope_location_ids=list(row.scope_location_ids),
            severity=row.severity,
            started_absolute=row.started_absolute,
            ends_absolute=row.ends_absolute,
            status=ConditionStatus(row.status),
            source_intervention_id=row.source_intervention_id,
            version=row.version,
        )

    async def add_condition(self, condition: WorldCondition) -> None:
        self._session.add(
            WorldConditionRow(
                id=condition.id,
                world_id=condition.world_id,
                kind=condition.kind.value,
                public_label=condition.public_label,
                detail=condition.detail,
                scope_location_ids=list(condition.scope_location_ids),
                severity=condition.severity,
                started_absolute=condition.started_absolute,
                ends_absolute=condition.ends_absolute,
                status=condition.status.value,
                source_intervention_id=condition.source_intervention_id,
                version=condition.version,
            )
        )
        await self._session.flush()

    async def get_condition(self, condition_id: WorldConditionId) -> WorldCondition:
        row = await self._session.get(WorldConditionRow, condition_id)
        if row is None:
            raise missing("world condition", condition_id)
        return self._to_domain(row)

    async def list_for_world(self, world_id: UUID) -> list[WorldCondition]:
        rows = (
            await self._session.execute(
                select(WorldConditionRow)
                .where(WorldConditionRow.world_id == world_id)
                .order_by(WorldConditionRow.started_absolute)
            )
        ).scalars()
        return [self._to_domain(row) for row in rows]

    async def list_active_for_world(self, world_id: UUID) -> list[WorldCondition]:
        rows = (
            await self._session.execute(
                select(WorldConditionRow).where(
                    WorldConditionRow.world_id == world_id,
                    WorldConditionRow.status == ConditionStatus.ACTIVE.value,
                )
            )
        ).scalars()
        return [self._to_domain(row) for row in rows]

    async def save_condition(
        self, condition: WorldCondition, expected_version: int
    ) -> WorldCondition:
        row = await self._session.get(WorldConditionRow, condition.id)
        if row is None:
            raise missing("world condition", condition.id)
        if row.version != expected_version:
            raise version_conflict("world condition", condition.id, expected_version, row.version)
        row.status = condition.status.value
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_domain(row)
