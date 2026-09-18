# Pixelsaga (worldsim)

A simulation engine for persistent, multi-generation story worlds. Detailed
phase-by-phase play (intents, reactions, model-resolved outcomes, narrated
beats) compresses into deterministic macro periods (days to years) when
nothing needs a model call, then returns to detail at seeded major events.
Lineage, focus succession, era digests, and end conditions carry canon
across the compression boundary with full event provenance.

## Layout

- `backend/` FastAPI + SQLAlchemy service. `src/worldsim/` layers:
  `domain` (frozen Pydantic contracts), `application` (orchestration,
  transactions, macro engine, ports), `infrastructure` (repositories,
  model gateway, settings), `interfaces` (HTTP routes, schemas, CLI).
- `frontend/` Vue 3 + Vite dev harness: scene, party, timeline, map,
  diary, relations, ops, generations.
- `content/` Seeds, schemas (regenerated domain JSON Schema, OpenAPI,
  TypeScript client), genre definitions.
- `implementation-plan/` The staged build plan (stages 0 to 5).
- `evidence/` Per-stage gate bundles. Local only, except
  `stage3-live-v1`.
- `compose.yaml` Postgres (pgvector) plus the production API image.

## Prerequisites

- Python 3.12 with `uv`, Node 24, Docker with compose, Postgres 16
  with pgvector (or `docker compose up db`).
- Copy `.env.example` to `.env`. Never commit `.env`.

## Run it

```sh
cp .env.example .env
docker compose up -d db             # postgres on 5432
make sync                           # backend deps
uv run --project backend --group dev alembic -c backend/alembic.ini upgrade head
make api                            # API on 127.0.0.1:8000
cd frontend && npm install && npm run dev   # UI on 5174
node verify.mjs http://localhost:5174       # end to end smoke, 10 checks
```

`verify.mjs` expects a fresh database. On a used DB, reset first:
drop and recreate `worldsim`, then `alembic upgrade head`.

## Check it

```sh
make test          # full backend suite (453 tests, ~25 min)
make lint          # ruff check + format check
make typecheck     # strict basedpyright
make contracts     # regen domain-schema.json, openapi.json, worldsim.ts
make migration-status
```

Frontend: `npm run typecheck`, `npm run build`. Backend migrations live
in `backend/migrations/versions/` (head `0029`); never edit a landed
migration, always add one.

## Configure it

Settings bind from `WORLDSIM_` env with `__` nesting (see
`.env.example`). Model calls go through a provider-neutral gateway:
scripted fake by default, OpenRouter live via `docs/LIVE_RUNBOOK.md`
(manual, never a gate). The frontend speaks to the API with an
optional bearer key persisted from the toolbar key field.

## Operate it

- Auth: a public bind refuses to start without
  `WORLDSIM_SECURITY__PUBLIC_BIND_ALLOW=true` plus a non-empty
  `WORLDSIM_SECURITY__API_KEY`. When a key is set, every request
  outside the health probes needs `Authorization: Bearer <key>`.
- Deploy: `docker build -f backend/Dockerfile -t worldsim-api .`, then
  `docker compose up -d api`. The entrypoint migrates before serving;
  readiness reports database, migration, extension, seed, and profile
  checks.
- Web: `docker compose up -d web` serves the production bundle on
  `${WEB_PORT:-8080}` with `/api` proxied to the API service and SPA
  fallback for deep links. No bearer secrets ship in the bundle; the
  key field persists locally in the browser.
- Back up: `make backup` dumps to `backups/` (gitignored).
  `make restore-check BACKUP=backups/<file>.sql` restores into a
  scratch database and compares event, world, and alembic counts.
  A backup counts as valid only after a restore check passes.

## How it got here

- Stage 0: domain contracts, persistence, gateway, HTTP boundary.
- Stage 1: three-phase autonomous play with evidence.
- Stage 2: seven-day perspective simulation (diary, relations, ops).
- Stage 3: thirty-day memory, v2 verbs, provider hardening, judged
  narration quality, 300-phase gate.
- Stage 5: macro engine, salience selection, genealogy with gated
  focus succession, era digests, end conditions, generation scenario
  gate, generations UI, version-store lockstep fixes. Audited in
  `evidence/stage5-hard-gate/REPORT.md`.
- Hardening: bearer-key enforcement, deploy image, verified backup
  round trip. Stage 4 (local model topology) is deferred, pending
  hardware.
- Revamp: Adventure Journal plus World Observatory over capability
  policy, presentation/chronicle contracts, asset pipeline with
  curated starter art, single-writer admission, durable intervention
  queue, linked creation, and persistent world conditions. Roles:
  Watch, Direct, God, Play. See `docs/pixelsaga-revamp/HANDOFF.md`.

`perchance-ver/` and `MONOLITH_MIGRATION_REFERENCE.md` are the legacy
monolith and its migration notes, kept for reference only.
