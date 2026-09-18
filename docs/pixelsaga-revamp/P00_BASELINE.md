# P00 baseline (18 September 2026)

Reviewed commit: `9f49f8e`. Local HEAD is `9f49f8e`; `git diff` against it
is empty. Only delta is untracked `docs/pixelsaga-revamp/`.

## Versions

- Backend interpreter: Python 3.12.13 via uv; worldsim 0.1.0;
  pydantic 2.13.5; provider profile `fake`.
- System python is 3.14.7; do not use it for backend work.
- Node v24.19.0; frontend has no lockfile pin beyond package.json ranges.

## Startup commands (pinned ports)

- DB: `docker compose up -d db` (postgres 5432).
- Migrate: `uv run --project backend --group dev alembic -c backend/alembic.ini upgrade head`.
- API: `make api` serves `worldsim.interfaces.cli serve` on 127.0.0.1:8000.
- Frontend: `cd frontend && npm run dev` serves Vite default 5173
  (README's 5174 requires `--port 5174 --strictPort`).
- Smoke: `node verify.mjs <base>`; the script body assumes backend 8100
  and `vite --port 5174`. Pin all three values per run.

## Test database identity

`migrated_db` (`backend/tests/conftest.py:124`) creates scratch database
`worldsim_stage0_test` from `WORLDSIM_DATABASE__URL`, upgrades to head,
and drops it after the test. Never point test runs at `worldsim`.

## Provider configuration

- Default profile is `fake`; Stage 0 scripted path stays fake and only
  Stage 1 roles follow the active profile
  (`infrastructure/model_gateway/selection.py`).
- OpenRouter requires `WORLDSIM_PROVIDER__OPENROUTER_API_KEY`; live probe
  is opt-in (`WORLDSIM_MODEL_LIVE_PROBE=1`), capped, never a gate.
- No live image provider exists. Supplied curated assets in
  `docs/pixelsaga-revamp/assets/images/` resolve the P04 starter-art
  source; live generation stays an integration limitation.

## Current DTOs (entry points, not exhaustive)

- HTTP schemas: `backend/src/worldsim/interfaces/http/schemas.py`
  (`SeedResponse`, `AdvanceResponse`, `MapPlace.occupants: list[str]`,
  `TimelineResponse.next_after: int`).
- Generated client: `content/clients/worldsim.ts` via `make contracts`.
- Seed fixtures: `content/seeds/stage0/` (Ember Vale; Hearth, Market;
  Wren, Ash).

## Known baseline failures (pre-existing, not revamp regressions)

- `make migration-status` FAILS: alembic check detects unmigrated model
  drift (`remove_table relationship`, `remove_index
  ix_relationship_world_id`, truncated output in artifact). The models
  dropped the `relationship` table without a migration. P03/P11 must
  decide: land a migration or restore the model, before claiming
  migration-clean.
- Full backend suite not run for this baseline (453 tests, ~25 min);
  last green run recorded in stage-close commits.

## References in force

- `references/player-sunlit-journal.png`,
  `references/watcher-world-observatory.png`: visual direction only.
- Styling supersession: warm ivory/teal/gold replaces black/white-only
  and pixel-art styling for this revamp. Static-mock gate, KISS, type
  safety, minimal copy, no perpetual animation, architecture boundaries,
  and verification requirements stay.

## Unresolved providers

- Live text/model provider: none configured; fake by default.
- Live image provider: none; curated assets supplied instead.
