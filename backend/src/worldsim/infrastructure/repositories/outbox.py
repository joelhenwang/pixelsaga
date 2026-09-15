"""Transactional outbox adapter (owned by S0-UOW-001).

Acknowledgement is idempotent: repeating it for an acked message
succeeds without effect; only failed messages refuse it.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.enums import OutboxState
from worldsim.domain.tasks import OutboxMessage
from worldsim.infrastructure.models.tasks import OutboxMessageRow
from worldsim.infrastructure.repositories._common import missing


def _to_domain(row: OutboxMessageRow) -> OutboxMessage:
    return OutboxMessage(
        id=row.id,
        world_id=row.world_id,
        event_id=row.event_id,
        kind=row.kind,
        payload=dict(row.payload),
        idempotency_key=row.idempotency_key,
        state=OutboxState(row.state),
        created_at=row.created_at,
    )


class SqlAlchemyOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, message: OutboxMessage) -> None:
        self._session.add(
            OutboxMessageRow(
                id=message.id,
                world_id=message.world_id,
                event_id=message.event_id,
                kind=message.kind,
                payload=dict(message.payload),
                idempotency_key=message.idempotency_key,
                state=message.state.value,
                created_at=message.created_at,
            )
        )
        await self._session.flush()

    async def claim_due(self, limit: int) -> list[OutboxMessage]:
        rows = (
            await self._session.execute(
                select(OutboxMessageRow)
                .where(OutboxMessageRow.state == "pending")
                .order_by(OutboxMessageRow.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).scalars()
        claimed = list(rows)
        for row in claimed:
            row.state = "claimed"
        await self._session.flush()
        return [_to_domain(row) for row in claimed]

    async def ack(self, message_id: UUID) -> bool:
        row = (
            await self._session.execute(
                select(OutboxMessageRow).where(OutboxMessageRow.id == message_id).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise missing("outbox message", message_id)
        if row.state == "acked":
            return True
        if row.state == "failed":
            return False
        row.state = "acked"
        await self._session.flush()
        return True

    async def fail(self, message_id: UUID) -> bool:
        row = await self._session.get(OutboxMessageRow, message_id)
        if row is None:
            raise missing("outbox message", message_id)
        if row.state not in ("pending", "claimed"):
            return False
        row.state = "failed"
        await self._session.flush()
        return True

    async def count_pending(self, world_id: UUID) -> int:
        value = (
            await self._session.execute(
                select(func.count(OutboxMessageRow.id)).where(
                    OutboxMessageRow.world_id == world_id,
                    OutboxMessageRow.state == "pending",
                )
            )
        ).scalar_one()
        assert isinstance(value, int)
        return value

    async def requeue_claimed(self) -> int:
        """Reset orphaned claims after a restart; acked/failed rows are final."""
        rows = (
            await self._session.execute(
                select(OutboxMessageRow)
                .where(OutboxMessageRow.state == "claimed")
                .with_for_update()
            )
        ).scalars()
        orphaned = list(rows)
        for row in orphaned:
            row.state = "pending"
        await self._session.flush()
        return len(orphaned)
