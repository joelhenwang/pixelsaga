"""Central optimistic-version store (owned by S0-UOW-001).

Compare-and-bump locks every requested row in canonical ID order inside
one statement, so concurrent writers serialize instead of deadlocking.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.application.ports.repositories import canonical_order
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.infrastructure.models.versions import AggregateVersionRow


class SqlAlchemyVersionStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, aggregate_id: UUID) -> int | None:
        row = await self._session.get(AggregateVersionRow, aggregate_id)
        return row.version if row is not None else None

    async def ensure(self, aggregate_id: UUID, world_id: UUID, kind: str) -> None:
        if await self._session.get(AggregateVersionRow, aggregate_id) is None:
            self._session.add(
                AggregateVersionRow(
                    aggregate_id=aggregate_id, world_id=world_id, kind=kind, version=0
                )
            )
            await self._session.flush()

    async def compare_and_bump(self, expected: dict[UUID, int]) -> dict[UUID, int]:
        ordered = canonical_order(list(expected))
        rows = (
            await self._session.execute(
                select(AggregateVersionRow)
                .where(AggregateVersionRow.aggregate_id.in_(ordered))
                .order_by(AggregateVersionRow.aggregate_id)
                .with_for_update()
            )
        ).scalars()
        locked = {row.aggregate_id: row for row in rows}
        for aggregate_id in ordered:
            if aggregate_id not in locked:
                raise DomainError(
                    ErrorCode.PRECONDITION_FAILED,
                    f"aggregate not registered: {aggregate_id}",
                )
            if locked[aggregate_id].version != expected[aggregate_id]:
                raise DomainError(
                    ErrorCode.VERSION_CONFLICT,
                    f"stale aggregate {aggregate_id}: "
                    f"expected={expected[aggregate_id]} actual={locked[aggregate_id].version}",
                )
        updated: dict[UUID, int] = {}
        for aggregate_id in ordered:
            locked[aggregate_id].version = expected[aggregate_id] + 1
            updated[aggregate_id] = locked[aggregate_id].version
        await self._session.flush()
        return updated

    async def check(self, expected: dict[UUID, int]) -> None:
        """Fail on stale aggregates without advancing versions.

        Reads validated without writes (communicate targets, spar
        partners) must not drift the store ahead of their rows.
        """
        ordered = canonical_order(list(expected))
        rows = (
            await self._session.execute(
                select(AggregateVersionRow)
                .where(AggregateVersionRow.aggregate_id.in_(ordered))
                .order_by(AggregateVersionRow.aggregate_id)
                .with_for_update()
            )
        ).scalars()
        locked = {row.aggregate_id: row for row in rows}
        for aggregate_id in ordered:
            if aggregate_id not in locked:
                raise DomainError(
                    ErrorCode.PRECONDITION_FAILED,
                    f"aggregate not registered: {aggregate_id}",
                )
            if locked[aggregate_id].version != expected[aggregate_id]:
                raise DomainError(
                    ErrorCode.VERSION_CONFLICT,
                    f"stale aggregate {aggregate_id}: "
                    f"expected={expected[aggregate_id]} actual={locked[aggregate_id].version}",
                )

    async def sync_version(
        self, aggregate_id: UUID, world_id: UUID, kind: str, version: int
    ) -> None:
        """Set the store to an applier-owned row version.

        Only the macro consequence applier uses this, immediately after
        writes that bypass canonical (birth/death/succession rows). It
        restores the row/store lockstep invariant so later canonical
        touches read live versions without conflict.
        """
        row = await self._session.get(AggregateVersionRow, aggregate_id)
        if row is None:
            self._session.add(
                AggregateVersionRow(
                    aggregate_id=aggregate_id, world_id=world_id, kind=kind, version=version
                )
            )
        else:
            row.version = version
        await self._session.flush()
