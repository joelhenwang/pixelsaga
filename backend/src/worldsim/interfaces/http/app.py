"""FastAPI application factory (owned by S0-API-001).

``create_app`` wires routes, middleware, handlers, and startup
reconciliation. The lifespan never applies migrations: it verifies the
process against durable state, requeues expired work, and reports.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

import worldsim
from worldsim.application.tasks.service import TaskService
from worldsim.domain.errors import DomainError
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.ops.logging import install
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.errors import (
    RequestIdMiddleware,
    domain_error_handler,
    unhandled_error_handler,
)
from worldsim.interfaces.http.routes import (
    activities,
    health,
    knowledge,
    operations,
    progress,
    relationships,
    roles,
    stage1,
    stage2,
    world,
)
from worldsim.interfaces.http.state import (
    MIGRATIONS_DIR,
    SEED_DIR,
    AppState,
    build_state,
    stage0_gateway,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    state: AppState = app.state.app_state
    install(state.settings)
    factory = state.uow_factory()
    report = await TaskService(factory).reconcile()
    app.state.startup_report = {
        "tasks_requeued": report.tasks_requeued,
        "outbox_requeued": report.outbox_requeued,
    }
    yield
    await state.engine.dispose()


def create_app(
    settings: Settings | None = None,
    *,
    seed_dir: Path | None = None,
    migrations_dir: Path | None = None,
    gateway_factory: Callable[[], FakeGateway] | None = None,
) -> FastAPI:
    resolved = settings if settings is not None else Settings()
    state = build_state(
        resolved,
        seed_dir=seed_dir if seed_dir is not None else SEED_DIR,
        migrations_dir=migrations_dir if migrations_dir is not None else MIGRATIONS_DIR,
        gateway_factory=gateway_factory if gateway_factory is not None else stage0_gateway,
    )
    app = FastAPI(
        title="worldsim",
        version=worldsim.__version__,
        lifespan=lifespan,
    )
    app.state.app_state = state
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(world.router, prefix="/api/v1")
    app.include_router(operations.router, prefix="/api/v1")
    app.include_router(stage1.router, prefix="/api/v1")
    app.include_router(activities.router, prefix="/api/v1")
    app.include_router(relationships.router, prefix="/api/v1")
    app.include_router(knowledge.router, prefix="/api/v1")
    app.include_router(progress.router, prefix="/api/v1")
    app.include_router(roles.router, prefix="/api/v1")
    app.include_router(stage2.router, prefix="/api/v1")
    return app
