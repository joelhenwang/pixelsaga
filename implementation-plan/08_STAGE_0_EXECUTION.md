# Stage 0 Execution Plan

**Stage ID:** `stage0-foundation-v1`
**Outcome:** A seeded world executes deterministic phase primitives and persists events, effects, observations, recent memories, task state, and outbox work with restart and duplicate safety.

## 1. Scope

Stage 0 proves the canonical write path before autonomous model behavior exists.

Included behavior:

- seed one small world;
- inspect world/clock/characters;
- advance one deterministic phase;
- execute scripted `WAIT`, `REST`, `OBSERVE`, and simple `MOVE` operations;
- validate and atomically commit typed effects;
- create perspective observations and recent memories;
- durably enqueue post-commit work;
- recover after injected process uncertainty;
- return the original result on duplicate delivery.

Excluded behavior:

- production character or Director graphs;
- interactive scene dialogue;
- combat, magic, injuries, and images;
- vector retrieval;
- production Vue UI;
- Temporal and distributed workers;
- PixelSaga compatibility.

## 2. Required implementation order

```text
S0-BOOT-001
 -> S0-CONFIG-001 + S0-QA-001
 -> S0-DOM-001
 -> S0-DB-001 + S0-MODEL-001
 -> S0-DB-002 + S0-SIM-001
 -> S0-UOW-001
 -> S0-TX-001 + S0-TASK-001 + S0-SEED-001
 -> S0-TRACE-001
 -> S0-ORCH-001
 -> S0-API-001 + S0-OPS-001
 -> S0-GATE-001
```

Database migrations have one owner at a time. Parallel lanes may implement pure domain rules, fakes, model protocols, and seed validation after shared contracts are frozen.

## 3. Task packets

### S0-BOOT-001: repository bootstrap

**Depends on:** none

**Owns:** root build files, `backend/` skeleton, command documentation, ignore rules

**Deliver:**

- Python 3.12 `uv` project;
- importable `worldsim` package with the layers in [02_SYSTEM_ARCHITECTURE.md](02_SYSTEM_ARCHITECTURE.md);
- baseline Pytest configuration;
- Docker Compose PostgreSQL service;
- commands for sync, migration, seed, test, stage scenario, API, and generated contracts;
- `.env.example` with names but no credentials.

**Verify:** clean dependency sync, package import, Docker Compose configuration parse, PostgreSQL readiness.

**Do not:** add placeholder domain services or frontend scaffolding.

### S0-CONFIG-001: configuration and static quality

**Depends on:** S0-BOOT-001

**Owns:** settings, Ruff, strict basedpyright, pre-commit/static commands

**Deliver:**

- typed settings groups for application, database, provider, tracing, and security;
- local/test profiles;
- loopback bind default;
- validation that rejects unsafe public bind without explicit auth override;
- dependency/version reporting.

**Verify:** valid local/test settings; missing secrets permitted for fake-only test profile; invalid database URL, embedding dimension, and public bind fail with actionable errors; lint/type checks pass.

### S0-QA-001: deterministic test harness and fakes

**Depends on:** S0-BOOT-001

**Owns:** test fixtures and harness utilities

**Deliver:**

- fake operational clock;
- deterministic fictional clock fixture;
- seeded random-source port and fake;
- fake model gateway with scripted responses/errors;
- PostgreSQL integration fixture;
- network-block fixture enabled by default;
- process-boundary/fault-injection hooks;
- stage scenario harness skeleton.

**Verify:** fixtures self-test, isolate state, release leases/connections, and make no external request.

### S0-DOM-001: domain primitives and contracts

**Depends on:** S0-BOOT-001

**Owns:** `domain/` primitives, enums, commands, effects, events, state errors

**Deliver:**

- opaque IDs and schema-version types;
- ten-phase fictional calendar and absolute phase index;
- world, character, location, phase snapshot/run, task, event, effect, observation, recent-memory contracts;
- command/idempotency/expected-version context;
- `WAIT`, `REST`, `OBSERVE`, simple `MOVE`, resource update, and memory effect schemas;
- stable error taxonomy;
- generated JSON Schema.

**Verify:** strict parsing, forbidden extra fields, enum/range constraints, JSON round trips, and import architecture.

**Do not:** import ORM, FastAPI, LangChain, or LangGraph.

### S0-DB-001: database and Alembic baseline

**Depends on:** S0-CONFIG-001, S0-DOM-001

**Owns:** async engine/session, Alembic environment, initial extension migration

**Deliver:**

- SQLAlchemy 2 async engine/session factory;
- deterministic naming convention;
- Alembic setup with one head;
- PostgreSQL and pgvector extension verification;
- migration status/verification command.

**Verify:** upgrade empty database, downgrade where supported, re-upgrade, detect multiple heads, and close connections cleanly.

### S0-DB-002: Stage 0 schema

**Depends on:** S0-DB-001

**Owns:** Stage 0 ORM mappings and migration

**Deliver:** only tables exercised by the Stage 0 scenario from [03_DOMAIN_AND_PERSISTENCE.md](03_DOMAIN_AND_PERSISTENCE.md), with foreign keys, uniqueness, checks, optimistic versions, event sequence, and idempotency constraints.

**Verify:** real database rejects duplicate world event sequence, effect ordinal, command key/input conflict, phase snapshot mutation, invalid ranges, and missing source links.

**Do not:** add Stage 1 scene/intent tables or unused vector columns.

### S0-SIM-001: deterministic time and primitive effects

**Depends on:** S0-DOM-001

**Owns:** pure World Engine rules and projectors for Stage 0

**Deliver:**

- ordered phase transition and day rollover;
- deterministic `WAIT`, `REST`, `OBSERVE`, simple `MOVE` feasibility;
- resource bounds;
- effect validation and pure projection operations;
- invariant registry;
- deterministic random evidence contract.

**Verify:** focused examples plus property/state-machine tests for phase ordering, invalid transitions, resource bounds, route access, and repeated projection determinism.

### S0-UOW-001: unit of work and repository ports

**Depends on:** S0-DB-002

**Owns:** application repository protocols, SQLAlchemy implementations, UoW

**Deliver:**

- explicit repository ports for Stage 0 aggregates;
- SQLAlchemy adapters returning domain/application DTOs, not ORM objects;
- transaction context owned by application service;
- optimistic version operations;
- deterministic lock ordering helper or policy.

**Verify:** real database CRUD/query, rollback, stale-version conflict, and concurrent update behavior.

### S0-TX-001: atomic event/effect commit

**Depends on:** S0-UOW-001, S0-SIM-001

**Owns:** canonical transaction service

**Deliver:** algorithm defined in [03_DOMAIN_AND_PERSISTENCE.md](03_DOMAIN_AND_PERSISTENCE.md), including idempotency lookup, input hash, version check, event/effect inserts, projections, observations, recent memories, outbox, and one commit.

**Verify:**

- success creates one coherent result;
- validation failure creates no event;
- exception at each pre-commit step rolls back all rows;
- duplicate request returns original result;
- same key/different input conflicts;
- crash after DB commit/before acknowledgement resolves by lookup;
- two stale writers cannot both commit.

### S0-TASK-001: task leases and transactional outbox

**Depends on:** S0-DB-002

**Owns:** task/outbox application services and Stage 0 in-process worker

**Deliver:**

- task creation and optional dependency record only if Stage 0 uses it;
- atomic claim with lease owner/expiry;
- heartbeat;
- bounded retry with deterministic backoff policy;
- terminal and dead-letter states;
- outbox claim and idempotent acknowledgement;
- late-owner protection;
- startup reconciler.

**Verify:** two-worker claim race, lease expiry/reclaim, duplicate consumer delivery, terminal-state protection, and process restart.

### S0-SEED-001: seed source and importer

**Depends on:** S0-DOM-001, S0-DB-002, S0-UOW-001

**Owns:** `content/seeds/` Stage 0 subset and importer

**Deliver:**

- deterministic seed version and IDs;
- one world, two characters, two locations, one route, public lore, and one private-secret fixture;
- schema/reference/license validation report;
- atomic import and `WORLD_SEEDED` event;
- idempotent repeat behavior.

**Verify:** empty import, repeated import, broken reference rollback, duplicate ID rejection, and secret ownership fixture.

### S0-MODEL-001: model gateway protocol and fake adapter

**Depends on:** S0-CONFIG-001, S0-DOM-001, S0-QA-001

**Owns:** application model port, model/profile result contracts, fake/OpenRouter adapters

**Deliver:**

- provider-neutral completion, embedding, and probe protocols;
- normalized timeout, rate-limit, unavailable, malformed, refusal, and capability errors;
- versioned model profiles;
- scripted fake adapter;
- OpenRouter adapter/probe behind opt-in configuration;
- no provider SDK escape.

**Verify:** fake success/error/usage behavior and mocked HTTP contract. Live probe is manual/opt-in, capped, and not a promotion gate.

**Do not:** create production character prompts or graphs.

### S0-TRACE-001: context and trace audit skeleton

**Depends on:** S0-DB-002, S0-MODEL-001

**Owns:** context-manifest/model-call persistence ports and optional LangSmith configuration

**Deliver:**

- minimal deterministic Context Manifest for Stage 0 fake calls;
- durable model-call lifecycle records;
- correlation identifiers from phase/task to call;
- redaction policy;
- optional LangSmith trace smoke with tags/metadata;
- behavior unchanged when LangSmith is disabled.

**Verify:** fake call trace joins correctly; secrets are absent from logs/export; disabled external tracing still records durable local audit.

### S0-ORCH-001: deterministic phase runner and reconciler

**Depends on:** S0-TX-001, S0-TASK-001, S0-SEED-001, S0-TRACE-001

**Owns:** phase orchestration application service

**Deliver:**

- create phase run;
- execute deterministic world tick;
- seal snapshot;
- execute scripted Stage 0 actions/effects;
- commit events/observations/recent memory/outbox;
- finalize phase;
- pause/reconcile incomplete work;
- prevent next phase while current is incomplete.

**Verify:** restart at every state boundary, no duplicate phase/event/effect, and deterministic result from identical seed/input.

### S0-API-001: minimal API and CLI

**Depends on:** S0-ORCH-001

**Owns:** FastAPI lifespan/routes/DTOs and CLI commands

**Deliver:** endpoints and CLI in [05_API_AND_FRONTEND.md](05_API_AND_FRONTEND.md), request IDs, stable errors, idempotency handling, generated OpenAPI, readiness dependency checks.

**Verify:** seed, inspect, advance, events, task status, and reconcile through the real boundary. Invalid/stale/duplicate commands return defined results.

### S0-OPS-001: observability and security baseline

**Depends on:** S0-CONFIG-001, S0-API-001

**Owns:** structured logging, redaction, health, audit configuration

**Deliver:**

- JSON-capable structured logs;
- request/command/phase/task/model correlation IDs;
- dependency readiness;
- secret redaction;
- loopback-safe launch defaults;
- process/version/schema/seed details in diagnostic output without credentials.

**Verify:** API key and connection password never appear in logs, exceptions, generated contracts, or evidence bundles.

### S0-GATE-001: foundation scenario and review

**Depends on:** all Stage 0 tasks

**Owns:** final stage scenario, reports, generated evidence

**Deliver:** `stage0-foundation-v1` scenario, fault report, migration report, consistency audit, architecture check, security check, and evidence index.

**Verify:** all hard exit criteria below.

## 4. Deterministic demonstration

1. Start PostgreSQL and application from a clean checkout.
2. Upgrade migrations.
3. Import the Stage 0 seed.
4. Display world, two characters, two locations, clock, and initial event cursor.
5. Advance one phase using a fixed idempotency key.
6. Execute scripted WAIT/REST/OBSERVE/MOVE effects.
7. Display event/effect timeline, character observations, recent memories, task state, and outbox state.
8. Inject termination after commit but before acknowledgement.
9. Restart and reconcile.
10. Repeat the same command/key.
11. Prove the original result is returned and row/event/effect counts do not increase.
12. Run the consistency audit.

## 5. Hard exit gate

All must pass:

- clean bootstrap and package import;
- empty and prior-fixture migrations with one head;
- seed import atomic and idempotent;
- deterministic phase progression and immutable snapshot;
- canonical event/effects/projections/observations/recent memory commit together;
- duplicate command/task produces no duplicate canon;
- crash after commit/before acknowledgement returns existing result;
- two workers cannot own one live task lease;
- expired task is safely reclaimed;
- next phase cannot start over partial current phase;
- strict contracts generate schemas;
- fake provider path works with no network;
- optional OpenRouter probe is isolated and capped;
- LangSmith disabled path behaves identically;
- zero hard consistency violations;
- architecture, lint, type, focused test, migration, and security checks pass;
- no secret appears in logs or generated artifacts.

## 6. Frozen handoff

Freeze and record:

- migration head;
- Stage 0 seed version;
- command/effect/event/context/model profile schemas;
- task lease and idempotency semantics;
- model gateway interface;
- canonical transaction interface;
- generated OpenAPI and JSON Schema;
- evidence bundle location;
- known non-hard limitations.

Stage 1 may extend these through explicit schema versions and migrations but may not bypass them.