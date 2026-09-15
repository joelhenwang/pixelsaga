"""Location repository adapter (owned by S0-UOW-001)."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import LocationId
from worldsim.domain.world import Location, Route
from worldsim.infrastructure.models.world import EntityRow, LocationRow
from worldsim.infrastructure.repositories._common import missing, version_conflict


def _routes_to_domain(raw: list[object]) -> list[Route]:
    routes: list[Route] = []
    for item in raw:
        if not isinstance(item, dict):
            raise DomainError(ErrorCode.VALIDATION_FAILED, "route must be an object")
        mapping = cast("dict[str, Any]", item)
        route_id = mapping["id"]
        destination = mapping["destination_location_id"]
        if not isinstance(route_id, str) or not isinstance(destination, str):
            raise DomainError(ErrorCode.VALIDATION_FAILED, "route ids must be strings")
        duration = mapping["duration_phases"]
        cost = mapping["stamina_cost"]
        if not isinstance(duration, int) or not isinstance(cost, int):
            raise DomainError(ErrorCode.VALIDATION_FAILED, "route numbers must be ints")
        routes.append(
            Route(
                id=LocationId(route_id),
                destination_location_id=LocationId(destination),
                duration_phases=duration,
                stamina_cost=cost,
            )
        )
    return routes


def _routes_to_row(routes: list[Route]) -> list[object]:
    return [
        {
            "id": str(route.id),
            "destination_location_id": str(route.destination_location_id),
            "duration_phases": route.duration_phases,
            "stamina_cost": route.stamina_cost,
        }
        for route in routes
    ]


def _to_domain(row: LocationRow) -> Location:
    return Location(
        id=row.id,
        world_id=row.world_id,
        name=row.name,
        region=row.region,
        capacity=row.capacity,
        routes=_routes_to_domain(row.routes),
        discovered=row.discovered,
        version=row.version,
    )


class SqlAlchemyLocationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, location_id: UUID) -> Location:
        row = await self._session.get(LocationRow, location_id)
        if row is None:
            raise missing("location", location_id)
        return _to_domain(row)

    async def list_for_world(self, world_id: UUID) -> list[Location]:
        rows = (
            await self._session.execute(
                select(LocationRow)
                .where(LocationRow.world_id == world_id)
                .order_by(LocationRow.name)
            )
        ).scalars()
        return [_to_domain(row) for row in rows]

    async def add(self, location: Location) -> None:
        self._session.add(
            EntityRow(
                id=location.id,
                world_id=location.world_id,
                kind="location",
                created_phase_index=0,
            )
        )
        await self._session.flush()
        self._session.add(
            LocationRow(
                id=location.id,
                world_id=location.world_id,
                name=location.name,
                region=location.region,
                capacity=location.capacity,
                routes=_routes_to_row(location.routes),
                discovered=location.discovered,
                version=location.version,
            )
        )
        await self._session.flush()

    async def save(self, location: Location, expected_version: int) -> Location:
        row = (
            await self._session.execute(
                select(LocationRow).where(LocationRow.id == location.id).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise missing("location", location.id)
        if row.version != expected_version:
            raise version_conflict("location", location.id, expected_version, row.version)
        row.name = location.name
        row.region = location.region
        row.capacity = location.capacity
        row.routes = _routes_to_row(location.routes)
        row.discovered = location.discovered
        row.version = expected_version + 1
        await self._session.flush()
        return location.model_copy(update={"version": expected_version + 1})
