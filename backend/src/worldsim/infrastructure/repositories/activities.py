"""Travel and activity adapter (owned by S2-CONTRACT-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.activities import Activity, TravelRoute
from worldsim.domain.enums import ActivityKind, ActivityStatus
from worldsim.domain.ids import ActivityId, RouteId
from worldsim.infrastructure.models.activities import ActivityRow, TravelRouteRow
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, row: ActivityRow) -> Activity:
        return Activity(
            id=row.id,
            world_id=row.world_id,
            character_id=row.character_id,
            kind=ActivityKind(row.kind),
            status=ActivityStatus(row.status),
            start_absolute=row.start_absolute,
            duration_phases=row.duration_phases,
            progress_phases=row.progress_phases,
            payload=dict(row.payload),
            version=row.version,
        )

    async def get(self, activity_id: ActivityId) -> Activity:
        row = await self._session.get(ActivityRow, activity_id)
        if row is None:
            raise missing("activity", activity_id)
        return self._to_domain(row)

    async def list_active_for_world(self, world_id: UUID) -> list[Activity]:
        rows = (
            await self._session.execute(
                select(ActivityRow)
                .where(ActivityRow.world_id == world_id, ActivityRow.status == "active")
                .order_by(ActivityRow.start_absolute)
            )
        ).scalars()
        return [self._to_domain(row) for row in rows]

    async def add(self, activity: Activity) -> None:
        self._session.add(
            ActivityRow(
                id=activity.id,
                world_id=activity.world_id,
                character_id=activity.character_id,
                kind=activity.kind.value,
                status=activity.status.value,
                start_absolute=activity.start_absolute,
                duration_phases=activity.duration_phases,
                progress_phases=activity.progress_phases,
                payload=dict(activity.payload),
                version=activity.version,
            )
        )
        await self._session.flush()

    async def save(self, activity: Activity, expected_version: int) -> Activity:
        row = await self._session.get(ActivityRow, activity.id)
        if row is None:
            raise missing("activity", activity.id)
        if row.version != expected_version:
            raise version_conflict("activity", activity.id, expected_version, row.version)
        row.status = activity.status.value
        row.start_absolute = activity.start_absolute
        row.progress_phases = activity.progress_phases
        row.payload = dict(activity.payload)
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_domain(row)


class SqlAlchemyRouteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, row: TravelRouteRow) -> TravelRoute:
        return TravelRoute(
            id=row.id,
            world_id=row.world_id,
            from_location_id=row.from_location_id,
            to_location_id=row.to_location_id,
            duration_phases=row.duration_phases,
            stamina_cost=row.stamina_cost,
            version=row.version,
        )

    async def list_for_world(self, world_id: UUID) -> list[TravelRoute]:
        rows = (
            await self._session.execute(
                select(TravelRouteRow).where(TravelRouteRow.world_id == world_id)
            )
        ).scalars()
        return [self._to_domain(row) for row in rows]

    async def add(self, route: TravelRoute) -> None:
        self._session.add(
            TravelRouteRow(
                id=route.id,
                world_id=route.world_id,
                from_location_id=route.from_location_id,
                to_location_id=route.to_location_id,
                duration_phases=route.duration_phases,
                stamina_cost=route.stamina_cost,
                version=route.version,
            )
        )
        await self._session.flush()

    async def save(self, route: TravelRoute, expected_version: int) -> TravelRoute:
        row = await self._session.get(TravelRouteRow, route.id)
        if row is None:
            raise missing("travel route", route.id)
        if row.version != expected_version:
            raise version_conflict("travel route", route.id, expected_version, row.version)
        row.duration_phases = route.duration_phases
        row.stamina_cost = route.stamina_cost
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_domain(row)

    async def remove(self, route_id: RouteId) -> None:
        row = await self._session.get(TravelRouteRow, route_id)
        if row is None:
            raise missing("travel route", route_id)
        await self._session.delete(row)
        await self._session.flush()
