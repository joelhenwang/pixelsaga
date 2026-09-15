"""Operational reads and recovery (owned by S0-API-001)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request

from worldsim.interfaces.http.schemas import (
    ReconcileRequest,
    ReconcileResponse,
    TaskResponse,
)

router = APIRouter(tags=["operations"])


@router.post("/operations/reconcile", response_model=ReconcileResponse)
async def reconcile(body: ReconcileRequest, request: Request) -> ReconcileResponse:
    state = request.app.state.app_state
    report = await state.orchestrator().reconcile_world(body.world_id)
    return ReconcileResponse(
        tasks_requeued=report.tasks_requeued,
        outbox_requeued=report.outbox_requeued,
        open_run_id=report.open_run_id,
        open_state=report.open_state,
    )


@router.get("/operations/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: UUID, request: Request) -> TaskResponse:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        task = await uow.tasks.get(task_id)
    lease = task.lease
    return TaskResponse(
        id=task.id,
        world_id=task.world_id,
        kind=task.kind,
        state=task.state.value,
        owner=lease.owner if lease is not None else None,
        attempt=lease.attempt if lease is not None else None,
        max_attempts=lease.max_attempts if lease is not None else None,
        expires_at=lease.expires_at if lease is not None else None,
    )
