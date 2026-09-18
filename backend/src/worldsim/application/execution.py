"""Shared per-world execution admission (owned by REVAMP-P06).

Phase, macro, and intervention application serialize through durable
task slots: exactly one owner executes a scope at a time. A loser gets
an explicit conflict carrying the in-progress run id, never a second
executor. Slots release on success; failures requeue after lease
expiry so a crashed owner cannot wedge the world.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from uuid import UUID, uuid4

from worldsim.application.orchestration.service import derive_run_id
from worldsim.application.tasks.service import TaskService
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.tasks import Lease, TaskRun
from worldsim.domain.time import utcnow

#: Execution lease per scope; model latency fits comfortably inside.
LEASE_SECONDS = 300


class SlotBusy(DomainError):
    """A scope is already executing; reconcile instead of retrying blindly."""


async def admit(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    scope: str,
    owner: str,
    run_id: UUID | None = None,
) -> TaskRun:
    """Claim the execution slot for one scope or raise SlotBusy."""
    service = TaskService(factory)
    key = f"execute:{world_id.hex}:{scope}"
    task = await service.create_task(world_id, "execution", key, max_attempts=10)
    now = utcnow()
    lease = Lease(
        owner=owner,
        claimed_at=now,
        expires_at=now + timedelta(seconds=LEASE_SECONDS),
        attempt=1,
        max_attempts=10,
        input_version=1,
        idempotency_key=key,
    )
    claimed = await service.claim_task(task.id, owner, lease)
    if claimed is None and await service.reset_slot(task.id, owner):
        claimed = await service.claim_task(task.id, owner, lease)
    if claimed is None:
        raise SlotBusy(
            ErrorCode.VERSION_CONFLICT,
            f"{scope} is already executing",
            {"run_id": str(run_id) if run_id is not None else None},
        )
    return claimed

async def release(factory: Callable[[], UnitOfWork], task: TaskRun, owner: str, ok: bool) -> None:
    """Release a held slot: success closes it, failure requeues it."""
    service = TaskService(factory)
    if ok:
        await service.succeed(task.id, owner)
    else:
        await service.fail_task(task.id, owner, retryable=True)


async def guarded[T](
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    scope: str,
    owner: str,
    run_id: UUID | None,
    work: Callable[[], Awaitable[T]],
) -> T:
    """Admit one scope, run the work, and release the slot either way."""
    slot = await admit(factory, world_id, scope, owner, run_id)
    try:
        result = await work()
    except Exception:
        await release(factory, slot, owner, False)
        raise
    await release(factory, slot, owner, True)
    return result


def phase_scope(index: int) -> str:
    """Admission scope for one detailed phase."""
    return f"phase:{index}"


def phase_run_id(world_id: UUID, index: int) -> UUID:
    """Deterministic run id shared by the slot conflict and the report."""
    return derive_run_id(world_id, index)


def new_owner(prefix: str) -> str:
    """Unique execution owner per attempt."""
    return f"{prefix}:{uuid4().hex[:12]}"
