"""Liveness and readiness (owned by S0-API-001; checks owned by S0-OPS-001)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from worldsim.infrastructure.ops.readiness import check_readiness
from worldsim.interfaces.http.schemas import DependencyCheck, HealthLiveResponse, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthLiveResponse)
async def live() -> HealthLiveResponse:
    return HealthLiveResponse()


@router.get("/health/ready", response_model=ReadyResponse)
async def ready(request: Request) -> ReadyResponse:
    state = request.app.state.app_state
    report = await check_readiness(state.engine, state.settings, state.migrations_dir)
    failed = any(check.status == "failed" for check in report.checks)
    return ReadyResponse(
        status="degraded" if failed or report.status == "degraded" else "ready",
        version=report.version,
        environment=report.environment,
        migration_head=report.migration_head,
        schema_version=report.schema_version,
        checks=[
            DependencyCheck(name=check.name, status=check.status, detail=check.detail)
            for check in report.checks
        ],
    )
