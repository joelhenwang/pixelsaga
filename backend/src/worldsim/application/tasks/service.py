"""Task leases, outbox delivery, and the in-process worker (owned by S0-TASK-001)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from worldsim.application.tasks.backoff import backoff_s
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.tasks import Lease, OutboxMessage, TaskRun


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ReconcileReport:
    tasks_requeued: int
    outbox_requeued: int


@dataclass(frozen=True)
class DrainReport:
    claimed: int
    acked: int
    failed: int


class TaskService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    async def create_task(
        self, world_id: UUID, kind: str, key: str, max_attempts: int = 3
    ) -> TaskRun:
        async with self._factory() as uow:
            existing = await uow.tasks.find_by_key(world_id, key)
            if existing is not None:
                if existing.kind != kind:
                    raise DomainError(
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        f"task key reused for another kind: {key}",
                    )
                return existing
            try:
                task = await uow.tasks.create(uuid4(), world_id, kind, key, max_attempts)
                await uow.commit()
            except IntegrityError:
                await uow.rollback()
                raced = await uow.tasks.find_by_key(world_id, key)
                if raced is None or raced.kind != kind:
                    raise DomainError(
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        f"task key reused for another kind: {key}",
                    ) from None
                return raced
            return task

    async def claim_available(
        self, kind: str | None, owner: str, lease_s: float, limit: int = 1
    ) -> list[TaskRun]:
        async with self._factory() as uow:
            claimed = await uow.tasks.claim_due(kind, owner, lease_s, limit)
            await uow.commit()
            return claimed

    async def claim_task(self, task_id: UUID, owner: str, lease: Lease) -> TaskRun | None:
        """Claim one task by ID: pending or expired leases move to running."""
        async with self._factory() as uow:
            claimed = await uow.tasks.claim(task_id, owner, lease)
            await uow.commit()
            return claimed

    async def reset_slot(self, task_id: UUID, owner: str) -> bool:
        """Recycle a terminal execution slot for a new cycle."""
        async with self._factory() as uow:
            ok = await uow.tasks.reset(task_id, owner)
            await uow.commit()
            return ok

    async def heartbeat(self, task_id: UUID, owner: str, lease_s: float) -> bool:
        async with self._factory() as uow:
            ok = await uow.tasks.heartbeat(task_id, owner, _utcnow() + timedelta(seconds=lease_s))
            await uow.commit()
            return ok

    async def succeed(self, task_id: UUID, owner: str) -> bool:
        async with self._factory() as uow:
            ok = await uow.tasks.finish(task_id, owner, "succeeded")
            await uow.commit()
            return ok

    async def fail_task(self, task_id: UUID, owner: str, retryable: bool) -> TaskRun:
        async with self._factory() as uow:
            task = await uow.tasks.get(task_id)
            if task.lease is None or task.lease.owner != owner:
                raise DomainError(
                    ErrorCode.PRECONDITION_FAILED,
                    "only the lease owner fails a running task",
                )
            attempt = task.lease.attempt
            if not retryable or attempt >= task.lease.max_attempts:
                state, expires = "dead_letter", None
            else:
                state = "retry_wait"
                expires = _utcnow() + timedelta(seconds=backoff_s(attempt + 1))
            if not await uow.tasks.fail(task_id, owner, state, expires):
                raise DomainError(
                    ErrorCode.PRECONDITION_FAILED,
                    "task already left the running state",
                )
            await uow.commit()
            return await uow.tasks.get(task_id)

    async def reconcile(self) -> ReconcileReport:
        async with self._factory() as uow:
            tasks_requeued = await uow.tasks.requeue_expired(_utcnow())
            outbox_requeued = await uow.outbox.requeue_claimed()
            await uow.commit()
            return ReconcileReport(tasks_requeued=tasks_requeued, outbox_requeued=outbox_requeued)


class OutboxService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    async def claim_batch(self, limit: int) -> list[OutboxMessage]:
        async with self._factory() as uow:
            claimed = await uow.outbox.claim_due(limit)
            await uow.commit()
            return claimed

    async def ack(self, message_id: UUID) -> bool:
        async with self._factory() as uow:
            ok = await uow.outbox.ack(message_id)
            await uow.commit()
            return ok

    async def fail(self, message_id: UUID) -> bool:
        async with self._factory() as uow:
            ok = await uow.outbox.fail(message_id)
            await uow.commit()
            return ok


Handler = Callable[[OutboxMessage], Awaitable[None]]


class InProcessWorker:
    """Stage 0 worker: drains claimed outbox messages through handlers."""

    def __init__(self, outbox: OutboxService, handlers: dict[str, Handler] | None = None) -> None:
        self._outbox = outbox
        self._handlers = dict(handlers) if handlers else {}

    def register(self, kind: str, handler: Handler) -> None:
        self._handlers[kind] = handler

    async def drain_once(self, limit: int = 10) -> DrainReport:
        claimed = await self._outbox.claim_batch(limit)
        acked = 0
        failed = 0
        for message in claimed:
            handler = self._handlers.get(message.kind)
            try:
                if handler is None:
                    raise DomainError(
                        ErrorCode.PRECONDITION_FAILED,
                        f"no handler for outbox kind: {message.kind}",
                    )
                await handler(message)
            except Exception:
                await self._outbox.fail(message.id)
                failed += 1
            else:
                await self._outbox.ack(message.id)
                acked += 1
        return DrainReport(claimed=len(claimed), acked=acked, failed=failed)
