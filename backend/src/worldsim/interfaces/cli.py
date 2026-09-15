"""Operator CLI mirroring the HTTP boundary (owned by S0-API-001).

Run from the repo root so relative content paths resolve::

    python -m worldsim.interfaces.cli seed
    python -m worldsim.interfaces.cli advance --world <id> --key <idempotency-key>
    python -m worldsim.interfaces.cli inspect world --world <id>
    python -m worldsim.interfaces.cli reconcile --world <id>
    python -m worldsim.interfaces.cli serve

Every command prints one JSON document to stdout. Domain failures print
a stable error envelope to stderr and exit 1.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

import worldsim
from worldsim.application.commands.seed_world import SeedService
from worldsim.application.orchestration.service import PhaseOrchestrator
from worldsim.application.tasks.service import TaskService
from worldsim.application.tracing.service import TraceService
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.domain.errors import DomainError
from worldsim.domain.time import absolute_index
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.ops.logging import install
from worldsim.infrastructure.repositories.unit_of_work import (
    SqlAlchemyUnitOfWork,
    create_unit_of_work,
)
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.tracing.langsmith import select_exporter
from worldsim.interfaces.http.state import SEED_DIR, stage0_gateway


def _json(document: object) -> str:
    return json.dumps(document, indent=2, sort_keys=True, default=str)


@dataclass
class Services:
    settings: Settings
    engine: AsyncEngine
    seed_dir: Path

    def uow(self) -> SqlAlchemyUnitOfWork:
        return create_unit_of_work(self.engine)

    def orchestrator(self) -> PhaseOrchestrator:
        factory = lambda: self.uow()  # noqa: E731
        return PhaseOrchestrator(
            factory,
            CanonicalTransaction(factory),
            TaskService(factory),
            TraceService(
                factory,
                select_exporter(
                    self.settings.tracing,
                    environment=self.settings.app.environment,
                    app_version=worldsim.__version__,
                ),
            ),
            stage0_gateway(),
        )


def _services(settings: Settings, seed_dir: Path) -> Services:
    return Services(settings=settings, engine=create_engine(settings), seed_dir=seed_dir)


async def _seed(services: Services) -> dict[str, object]:
    result = await SeedService(lambda: services.uow(), services.seed_dir).import_seed()
    return {
        "world_id": str(result.world_id),
        "seed_version": result.seed_version,
        "content_hash": result.content_hash,
        "duplicate": result.duplicate,
    }


async def _advance(services: Services, world_id: UUID, key: str) -> dict[str, object]:
    report = await services.orchestrator().advance_world(world_id, key)
    async with services.uow() as uow:
        world = await uow.worlds.get(world_id)
        cursor = await uow.events.max_sequence(world_id)
    return {
        "command_id": str(report.command_id),
        "run_id": str(report.run_id),
        "task_id": str(report.task_id),
        "world_version": world.version,
        "event_cursor": cursor,
        "idempotent_replay": report.duplicate,
        "event_id": str(report.event_id),
        "sequence": report.sequence,
    }


async def _inspect_world(services: Services, world_id: UUID) -> dict[str, object]:
    async with services.uow() as uow:
        world = await uow.worlds.get(world_id)
        characters = await uow.characters.list_for_world(world_id)
        locations = await uow.locations.list_for_world(world_id)
        run = await uow.phases.find_open_run(world_id)
        events = await uow.events.count_events(world_id)
    return {
        "world": {
            "id": str(world.id),
            "name": world.name,
            "day": world.day,
            "phase": world.phase.value,
            "absolute_index": absolute_index(world.day, world.phase),
            "version": world.version,
        },
        "characters": [
            {"id": str(character.id), "name": character.name, "version": character.version}
            for character in characters
        ],
        "locations": [{"id": str(location.id), "name": location.name} for location in locations],
        "open_run": (
            {"id": str(run.id), "state": run.state.value, "index": run.absolute_index}
            if run is not None
            else None
        ),
        "event_count": events,
    }


async def _inspect_events(
    services: Services, world_id: UUID, after: int, limit: int
) -> dict[str, object]:
    async with services.uow() as uow:
        events = await uow.events.list_range(world_id, after, limit)
        entries = [
            {
                "sequence": event.sequence,
                "id": str(event.id),
                "type": event.event_type.value,
                "effects": len(await uow.events.list_effects(event.id)),
            }
            for event in events
        ]
    return {"entries": entries, "next_after": entries[-1]["sequence"] if entries else after}


async def _inspect_task(services: Services, task_id: UUID) -> dict[str, object]:
    async with services.uow() as uow:
        task = await uow.tasks.get(task_id)
    lease = task.lease
    return {
        "id": str(task.id),
        "world_id": str(task.world_id),
        "kind": task.kind,
        "state": task.state.value,
        "owner": lease.owner if lease is not None else None,
        "attempt": lease.attempt if lease is not None else None,
    }


async def _reconcile(services: Services, world_id: UUID) -> dict[str, object]:
    report = await services.orchestrator().reconcile_world(world_id)
    return {
        "tasks_requeued": report.tasks_requeued,
        "outbox_requeued": report.outbox_requeued,
        "open_run_id": str(report.open_run_id) if report.open_run_id is not None else None,
        "open_state": report.open_state,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="worldsim", description="Stage 0 operator CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="Import the Stage 0 seed")
    seed.add_argument("--seed-dir", type=Path, default=SEED_DIR)

    advance = sub.add_parser("advance", help="Advance one phase")
    advance.add_argument("--world", type=UUID, required=True)
    advance.add_argument("--key", required=True, help="Idempotency key for this advance")
    advance.add_argument("--seed-dir", type=Path, default=SEED_DIR)

    inspect = sub.add_parser("inspect", help="Read projections")
    inspect_sub = inspect.add_subparsers(dest="target", required=True)
    inspect_world = inspect_sub.add_parser("world")
    inspect_world.add_argument("--world", type=UUID, required=True)
    inspect_events = inspect_sub.add_parser("events")
    inspect_events.add_argument("--world", type=UUID, required=True)
    inspect_events.add_argument("--after", type=int, default=0)
    inspect_events.add_argument("--limit", type=int, default=50)
    inspect_task = inspect_sub.add_parser("task")
    inspect_task.add_argument("--task", type=UUID, required=True)

    reconcile = sub.add_parser("reconcile", help="Requeue expired work and report open runs")
    reconcile.add_argument("--world", type=UUID, required=True)
    reconcile.add_argument("--seed-dir", type=Path, default=SEED_DIR)

    serve = sub.add_parser("serve", help="Serve the HTTP boundary")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "serve":
        return _serve(args)
    settings = Settings()
    install(settings)
    seed_dir = getattr(args, "seed_dir", SEED_DIR)
    services = _services(settings, seed_dir)
    try:
        if args.command == "seed":
            document = asyncio.run(_seed(services))
        elif args.command == "advance":
            document = asyncio.run(_advance(services, args.world, args.key))
        elif args.command == "inspect" and args.target == "world":
            document = asyncio.run(_inspect_world(services, args.world))
        elif args.command == "inspect" and args.target == "events":
            document = asyncio.run(_inspect_events(services, args.world, args.after, args.limit))
        elif args.command == "inspect" and args.target == "task":
            document = asyncio.run(_inspect_task(services, args.task))
        elif args.command == "reconcile":
            document = asyncio.run(_reconcile(services, args.world))
        else:
            raise AssertionError(f"unknown command: {args.command}/{getattr(args, 'target', None)}")
    except DomainError as exc:
        print(
            _json({"error": {"code": exc.code.value.upper(), "message": str(exc)}}),
            file=sys.stderr,
        )
        return 1
    finally:
        asyncio.run(services.engine.dispose())
    print(_json(document))
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from worldsim.interfaces.http.app import create_app

    settings = Settings()
    host = args.host or settings.app.host
    port = args.port or settings.app.port
    uvicorn.run(create_app(settings), host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
