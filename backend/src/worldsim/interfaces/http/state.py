"""Composition root for the HTTP boundary (owned by S0-API-001).

``AppState`` carries everything handlers need: settings, engine, seed
content, and factories for the gateway and external exporter. Routes
stay thin; services own rules.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine

import worldsim
from worldsim.application.orchestration.service import PhaseOrchestrator
from worldsim.application.orchestration.stage1 import Stage1Orchestrator
from worldsim.application.ports.traces import TraceExporter
from worldsim.application.tasks.service import TaskService
from worldsim.application.tracing.service import TraceService
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.domain.rules.dnd import DataTables, load_data
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import STAGE0_SCRIPTED_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import (
    SqlAlchemyUnitOfWork,
    create_unit_of_work,
)
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.tracing.langsmith import select_exporter

#: Static Stage 0 narration until a narrator role promotes past the fake.
STAGE0_DEFAULT_BEAT = "The watch turns over the vale; the company holds its course."

SEED_DIR = Path("content/seeds/stage0")

DND_DATA_DIR = Path("content/dnd")


_dnd_tables: DataTables | None = None


def dnd_tables() -> DataTables:
    """Vendored SRD tables, loaded once per process."""
    global _dnd_tables
    if _dnd_tables is None:
        _dnd_tables = load_data(DND_DATA_DIR)
    return _dnd_tables


def stage0_gateway() -> FakeGateway:
    return FakeGateway(profile=STAGE0_SCRIPTED_PROFILE, default_text=STAGE0_DEFAULT_BEAT)


@dataclass
class AppState:
    settings: Settings
    engine: AsyncEngine
    seed_dir: Path
    migrations_dir: Path
    gateway_factory: Callable[[], FakeGateway]
    exporter: TraceExporter

    def uow_factory(self) -> Callable[[], SqlAlchemyUnitOfWork]:
        engine = self.engine

        def _factory() -> SqlAlchemyUnitOfWork:
            return create_unit_of_work(engine)

        return _factory

    def tasks(self) -> TaskService:
        return TaskService(self.uow_factory())

    def traces(self) -> TraceService:
        return TraceService(self.uow_factory(), self.exporter)

    def orchestrator(self, gateway: FakeGateway | None = None) -> PhaseOrchestrator:
        factory = self.uow_factory()
        return PhaseOrchestrator(
            factory,
            CanonicalTransaction(factory),
            TaskService(factory),
            TraceService(factory, self.exporter),
            gateway if gateway is not None else self.gateway_factory(),
        )

    def stage1(self) -> Stage1Orchestrator:
        """Stage 1 orchestrator with per-role gateways and fake profiles."""
        from worldsim.infrastructure.model_gateway.profiles import (
            CHARACTER_FAKE_PROFILE,
            NARRATOR_FAKE_PROFILE,
            REACTION_FAKE_PROFILE,
            RESOLVER_FAKE_PROFILE,
        )

        factory = self.uow_factory()
        gateways = {
            role: self.gateway_factory()
            for role in ("character", "reaction", "resolver", "narrator")
        }

        def _for_role(role: str) -> FakeGateway:
            return gateways[role]

        return Stage1Orchestrator(
            factory,
            CanonicalTransaction(factory),
            TaskService(factory),
            TraceService(factory, self.exporter),
            _for_role,
            {
                "character": CHARACTER_FAKE_PROFILE,
                "reaction": REACTION_FAKE_PROFILE,
                "resolver": RESOLVER_FAKE_PROFILE,
                "narrator": NARRATOR_FAKE_PROFILE,
            },
        )


MIGRATIONS_DIR = Path("backend/migrations")


def build_state(
    settings: Settings,
    *,
    seed_dir: Path = SEED_DIR,
    migrations_dir: Path = MIGRATIONS_DIR,
    gateway_factory: Callable[[], FakeGateway] = stage0_gateway,
) -> AppState:
    exporter: TraceExporter = select_exporter(
        settings.tracing,
        environment=settings.app.environment,
        app_version=worldsim.__version__,
    )
    return AppState(
        settings=settings,
        engine=create_engine(settings),
        seed_dir=seed_dir,
        migrations_dir=migrations_dir,
        gateway_factory=gateway_factory,
        exporter=exporter,
    )
