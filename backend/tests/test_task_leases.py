import asyncio
import uuid
from collections.abc import AsyncGenerator, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from worldsim.application.tasks.backoff import backoff_s
from worldsim.application.tasks.service import (
    InProcessWorker,
    OutboxService,
    TaskService,
)
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_outbox_id, new_world_id
from worldsim.domain.tasks import OutboxMessage, TaskRun
from worldsim.domain.world import World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import (
    SqlAlchemyUnitOfWork,
    create_unit_of_work,
)
from worldsim.infrastructure.settings import Settings


def _factory_for(engine: AsyncEngine) -> Callable[[], SqlAlchemyUnitOfWork]:
    def _factory() -> SqlAlchemyUnitOfWork:
        return create_unit_of_work(engine)

    return _factory


@asynccontextmanager
async def _services() -> AsyncGenerator[tuple[TaskService, OutboxService]]:
    engine = create_engine(Settings())
    try:
        yield TaskService(_factory_for(engine)), OutboxService(_factory_for(engine))
    finally:
        await engine.dispose()


async def _seed_world() -> uuid.UUID:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            await uow.worlds.add(World(id=wid, name="Tasks", seed_version="s0-test"))
            await uow.commit()
            return wid
    finally:
        await engine.dispose()


def test_claim_race_has_single_winner(migrated_db: None) -> None:
    async def _inner() -> None:
        wid = await _seed_world()
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                task = await uow.tasks.create(uuid.uuid4(), wid, "phase_advance", "race-1")
                await uow.commit()
                task_id = task.id
        finally:
            await engine.dispose()

        outcomes: dict[str, list[TaskRun]] = {}

        def _race(owner: str) -> None:
            async def _claim() -> None:
                inner_engine = create_engine(Settings())
                try:
                    service = TaskService(_factory_for(inner_engine))
                    outcomes[owner] = await service.claim_available("phase_advance", owner, 60.0, 1)
                finally:
                    await inner_engine.dispose()

            asyncio.run(_claim())

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(_race, ("worker-a", "worker-b")))
        winners = [owner for owner, won in outcomes.items() if won]
        assert len(winners) == 1
        assert outcomes[winners[0]][0].id == task_id

    asyncio.run(_inner())


def test_expired_lease_reclaimed(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _services() as (tasks, _outbox):
            wid = await _seed_world()
            task = await tasks.create_task(wid, "phase_advance", "expiry-1")
            first = await tasks.claim_available("phase_advance", "worker-a", 0.0, 1)
            assert len(first) == 1
            second = await tasks.claim_available("phase_advance", "worker-b", 60.0, 1)
            assert len(second) == 1
            assert second[0].lease is not None
            assert second[0].lease.owner == "worker-b"
            assert second[0].lease.attempt == 2
            assert task.id == second[0].id

    asyncio.run(_inner())


def test_terminal_states_protected(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _services() as (tasks, _outbox):
            wid = await _seed_world()
            task = await tasks.create_task(wid, "phase_advance", "terminal-1")
            assert await tasks.claim_available("phase_advance", "worker-a", 60.0, 1)
            assert await tasks.succeed(task.id, "worker-a")
            assert not await tasks.succeed(task.id, "worker-a")
            with pytest.raises(DomainError) as excinfo:
                await tasks.fail_task(task.id, "worker-a", retryable=False)
            assert excinfo.value.code is ErrorCode.PRECONDITION_FAILED

    asyncio.run(_inner())


def test_retry_then_dead_letter(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _services() as (tasks, _outbox):
            wid = await _seed_world()
            doomed = await tasks.create_task(wid, "phase_advance", "doom-1", max_attempts=1)
            assert await tasks.claim_available("phase_advance", "worker-a", 60.0, 1)
            finished = await tasks.fail_task(doomed.id, "worker-a", retryable=True)
            assert finished.state.value == "dead_letter"
            retryable = await tasks.create_task(wid, "phase_advance", "retry-1", max_attempts=5)
            assert await tasks.claim_available("phase_advance", "worker-a", 60.0, 1)
            waiting = await tasks.fail_task(retryable.id, "worker-a", retryable=True)
            assert waiting.state.value == "retry_wait"
            assert waiting.lease is not None and waiting.lease.expires_at is not None

    asyncio.run(_inner())


def test_late_owner_rejected(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _services() as (tasks, _outbox):
            wid = await _seed_world()
            task = await tasks.create_task(wid, "phase_advance", "late-1")
            assert await tasks.claim_available("phase_advance", "worker-a", 60.0, 1)
            assert not await tasks.heartbeat(task.id, "worker-b", 60.0)
            assert not await tasks.succeed(task.id, "worker-b")
            assert await tasks.heartbeat(task.id, "worker-a", 60.0)
            assert await tasks.succeed(task.id, "worker-a")

    asyncio.run(_inner())


def test_reconcile_after_restart(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _services() as (tasks, _outbox):
            wid = await _seed_world()
            await tasks.create_task(wid, "phase_advance", "restart-1")
            assert await tasks.claim_available("phase_advance", "worker-a", 0.0, 1)
        async with _services() as (fresh_tasks, _fresh_outbox):
            report = await fresh_tasks.reconcile()
            assert report.tasks_requeued == 1
            claimed = await fresh_tasks.claim_available("phase_advance", "worker-b", 60.0, 1)
            assert len(claimed) == 1

    asyncio.run(_inner())


def test_outbox_duplicate_ack_and_worker(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _services() as (_tasks, outbox):
            wid = await _seed_world()
            engine = create_engine(Settings())
            try:
                async with create_unit_of_work(engine) as uow:
                    for key, kind in (("m-ok", "ok"), ("m-fail", "fail")):
                        await uow.outbox.add(
                            OutboxMessage(
                                id=new_outbox_id(),
                                world_id=wid,
                                event_id=None,
                                kind=kind,
                                payload={"n": 1},
                                idempotency_key=key,
                            )
                        )
                    await uow.commit()
            finally:
                await engine.dispose()
            seen: list[str] = []

            async def _ok(message: OutboxMessage) -> None:
                seen.append(message.kind)

            async def _boom(message: OutboxMessage) -> None:
                raise RuntimeError(f"cannot handle {message.kind}")

            worker = InProcessWorker(outbox, {"ok": _ok, "fail": _boom})
            report = await worker.drain_once(10)
            assert (report.claimed, report.acked, report.failed) == (2, 1, 1)
            assert seen == ["ok"]
            engine = create_engine(Settings())
            try:
                async with create_unit_of_work(engine) as uow:
                    assert await uow.outbox.count_pending(wid) == 0
                    claimed = await uow.outbox.claim_due(10)
                    assert claimed == []
            finally:
                await engine.dispose()

    asyncio.run(_inner())


def test_outbox_ack_is_idempotent(migrated_db: None) -> None:
    async def _inner() -> None:
        async with _services() as (_tasks, outbox):
            wid = await _seed_world()
            engine = create_engine(Settings())
            try:
                async with create_unit_of_work(engine) as uow:
                    message_id = new_outbox_id()
                    await uow.outbox.add(
                        OutboxMessage(
                            id=message_id,
                            world_id=wid,
                            event_id=None,
                            kind="ok",
                            payload={},
                            idempotency_key="m-1",
                        )
                    )
                    await uow.commit()
            finally:
                await engine.dispose()
            assert await outbox.claim_batch(10)
            assert await outbox.ack(message_id)
            assert await outbox.ack(message_id)

    asyncio.run(_inner())


def test_backoff_policy_and_idempotent_create(migrated_db: None) -> None:
    assert backoff_s(1) == 5.0
    assert backoff_s(2) == 10.0
    assert backoff_s(3) == 20.0
    assert backoff_s(40) == 600.0
    with pytest.raises(ValueError, match="starts at 1"):
        backoff_s(0)

    async def _inner() -> None:
        async with _services() as (tasks, _outbox):
            wid = await _seed_world()
            first = await tasks.create_task(wid, "phase_advance", "idem-1")
            second = await tasks.create_task(wid, "phase_advance", "idem-1")
            assert first.id == second.id
            with pytest.raises(DomainError) as excinfo:
                await tasks.create_task(wid, "other_kind", "idem-1")
            assert excinfo.value.code is ErrorCode.IDEMPOTENCY_CONFLICT

    asyncio.run(_inner())
