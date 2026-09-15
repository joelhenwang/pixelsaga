# Backend (worldsim)

Stage 0 bootstrap skeleton. See `implementation-plan/08_STAGE_0_EXECUTION.md`.

## Commands (run from repo root)

- `make sync` — `uv sync` for `backend/` on Python 3.12.
- `make test` — run Pytest (`backend/tests`, `pythonpath=src`).
- `make migration-status` — pending, owned by S0-DB-001.
- `make seed` — pending, owned by S0-SEED-001.
- `make stage-scenario` — pending, owned by S0-GATE-001.
- `make api` — pending, owned by S0-API-001.
- `make contracts-help` — pending, owned by S0-DOM-001 / S0-API-001.

## Layout

`src/worldsim/{domain,application,agents,infrastructure,interfaces}` are
importable layer markers only. Real code lands with the owning S0 task.

## Environment

Copy `../.env.example` to `../.env` for local Compose. Never commit `.env`.

## Settings (S0-CONFIG-001)

Typed groups in `src/worldsim/infrastructure/settings.py`: application,
database, provider, tracing, security. Environment names use prefix
`WORLDSIM_` with nested delimiter `__` (see `../.env.example`).
Loopback bind is the default; a public bind requires
`WORLDSIM_SECURITY__PUBLIC_BIND_ALLOW=true` plus a non-empty API key.

## Static quality

- `make lint` — Ruff check and format check.
- `make typecheck` — strict basedpyright (`pyrightconfig.json`).
- `make versions` — dependency and version report without secrets.

## Domain (S0-DOM-001)

Pure contracts in `src/worldsim/domain/`: IDs, enums, fictional calendar,
error taxonomy, commands, effects, events, world/character/phase/task state,
and perception records. Imports stdlib plus Pydantic v2 only.
Regenerate and verify the committed bundle with `make contracts`
(writes `content/schemas/domain-schema.json`).

## Database (S0-DB-001)

Async SQLAlchemy 2 engine/session in `src/worldsim/infrastructure/db/`,
declarative base with deterministic naming in
`src/worldsim/infrastructure/models/`, Alembic in `migrations/` (baseline
revision enables pgvector). `make migration-status` runs `alembic check`
plus `current`. Tables arrive with S0-DB-002.

## Model gateway (S0-MODEL-001)

Provider-neutral port in `src/worldsim/application/ports/`, scripted fake
and OpenRouter adapters plus versioned profiles in
`src/worldsim/infrastructure/model_gateway/`. No provider SDK; live probe
is manual (`WORLDSIM_MODEL_LIVE_PROBE=1`) and never a gate.

## Schema (S0-DB-002)

Stage 0 mappings in `src/worldsim/infrastructure/models/` plus migration
`0002_stage0_schema` (22 tables, FK/unique/check/idempotency constraints,
immutable snapshots via trigger). No Stage 1 tables, no vector columns.
`alembic check` must report no drift; seeds flush parents before children
because the mappings define no ORM relationships.

## Engine rules (S0-SIM-001)

Pure deterministic rules in `src/worldsim/domain/rules/`: ordered phase
transitions, action feasibility, effect planning, pure projectors,
invariant audits, and seeded random evidence. No I/O, no database, no
models; same inputs always give the same outputs.

## Unit of work (S0-UOW-001)

Repository ports in `src/worldsim/application/ports/` (domain models only,
expected-version saves), SQLAlchemy adapters plus `SqlAlchemyUnitOfWork` in
`src/worldsim/infrastructure/repositories/`. Version compare-and-bump
locks aggregates in canonical ID order; seeds flush parents first.

## Canonical transaction (S0-TX-001)

`CanonicalTransaction` in `src/worldsim/application/transactions/` commits
command, event, ordered effects, projections, observations, memories, and
outbox rows atomically. Duplicate keys return the stored result; changed
inputs conflict; faults before commit leave no rows.

## Tasks and outbox (S0-TASK-001)

`TaskService`, `OutboxService`, and the in-process worker in
`src/worldsim/application/tasks/`. Leases claim under row locks with
deterministic backoff; terminal states are final; `reconcile()` requeues
orphans after a restart. No task dependencies in Stage 0.

## Seed import (S0-SEED-001)

Stage 0 content in `content/seeds/stage0/` (fixed IDs, synthetic-original
license) plus `SeedService` in `src/worldsim/application/commands/`.
Validation precedes one atomic commit recording the WORLD_SEEDED event;
repeat imports return the stored world.

## Trace audit (S0-TRACE-001)

`TraceService` in `src/worldsim/application/tracing/` records a durable
`model_call` row plus one `context_manifest` per gateway call (migration
`0003_trace_correlation` adds role, phase/task/actor links, prompt hash,
profile and rendered-hash columns). Stored prompts/completions pass a
redaction policy masking keys, bearer tokens, connection strings, and
credential assignments. `LangSmithExporter` in
`src/worldsim/infrastructure/tracing/` is best-effort and hash-only;
`select_exporter` returns the null sink unless enabled with a key, and
disabled tracing records the identical local audit.

## Phase orchestration (S0-ORCH-001)

`PhaseOrchestrator` in `src/worldsim/application/orchestration/` advances
one phase per call: reconcile tasks, heal any run whose tick committed
before a crash (seal + finalize, then continue), ensure the run, claim
its task under a deterministic owner, trace a narrator call, commit the
clock tick, seal the snapshot, finalize. Run, command, task-key, and
snapshot IDs derive deterministically, so resume is re-entry and no
duplicate phase, event, effect, or snapshot can result. The task is a
crash-recovery lock (the run row carries failure state); pause gates
pre-commit runs only; terminal runs never auto-retry.

## HTTP boundary and CLI (S0-API-001)

FastAPI in `src/worldsim/interfaces/http/` (`create_app`, Stage 0
routers, DTOs, stable error envelopes, request IDs, committed
`content/schemas/openapi.json`). Advance requires `Idempotency-Key`;
repeating a key replays the stored tick result. Operator CLI in
`src/worldsim/interfaces/cli.py`: `seed`, `advance --world --key`,
`inspect world|events|task`, `reconcile`, `serve` (loopback; `make api`).

## Observability and security (S0-OPS-001)

Redacting JSON logs in `src/worldsim/infrastructure/ops/logging.py`
(correlation request IDs, secret values plus credential shapes masked),
readiness in `ops/readiness.py` (`GET /api/v1/health/ready`: database,
migration head, extensions, seed, profile; failure details carry type
names only). `make versions` prints a secret-free dependency report.

## Foundation scenario (S0-GATE-001)

`make stage-scenario` runs `test_stage0_foundation.py`: the twelve-step
demonstration (seed, inspect, fixed-key advance, scripted WAIT intents,
fault after commit, restart, reconcile, same-key replay with stable
counts, fresh-key progress, consistency audit) and writes
`evidence/stage0-foundation-v1/`. The audit in
`src/worldsim/application/operations/consistency.py` re-derives
deterministic run/snapshot/task IDs and reports violations; clean means
zero. The scenario also secret-scans the evidence plus committed
contracts.
