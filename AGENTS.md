I'm Joel. You're my AI agent.
I like to prototype complex ideas into simple, production ready apps.

# Coding preference:
- Keep things simple. "YAGNI", "KISS", "DRY" principles are preferred.
- Typesafety is useful, take advantage of it.
- Don't be scared to propose bold ideas, be they creative/innovative or common, as long as they will, very likely, meaningfully benefit the project.
- Tests should be focused, not slop (endless smoke tests, "regression tests" for feature deletion, etc... , not that good).
- Comments are a great way to explain how a code block or a code line works, as long as you don't overdo it.
- Interpretability is important. Make sure that variable and function names can be easily understood. Don't focus on using concise names, it's okay to use extended naming for the purpose of interpretability.
- Keep comments up to date.
- Avoid one line functions that are just casting wrappers.
- Avoid helper functions if they are not going to be reused. Only exception is when a code logic/workflow/pipeline benefits from having a separate helper function to help with readability, interpretability and maintainability.

## Coding preference (Typescript):
- `any` is frowned upon, avoid it.
- The implemented systems should be able to adapt changes, instead of requiring changes everywhere. Inferred types preferred.
- Typescript code that looks like Python code equals bad TypeScript code.
- Do not edit real components first. For any non-trivial UI, layout, or copy change, build distinct static mocks (HTML + embedded vanilla JavaScript) and stop. Wait for a pick before implementing.
- Standing constraints: true dark mode (`#000`), true white mode. Information dense, no decorative card/pill chrome, no light gray subtitle lines above sections. Minimal copy. No em dashes.
- Avoid continuously repainting CSS animations (pulse, shimmer, blur, spinners); GPU heavy

# This project (pixelsaga / worldsim)
Read `README.md` for the full picture. Facts that keep work fast:

- Backend layers: `domain` (frozen Pydantic, `extra="forbid"`), `application`
  (orchestration, transactions, ports), `infrastructure`, `interfaces`
  (HTTP + CLI). Domain never imports outside stdlib plus Pydantic.
- Every repository exists twice: a `Protocol` port in
  `application/ports/` plus the UoW property, and the SQLAlchemy impl
  in `infrastructure/repositories/` plus its UoW wiring. Add both or
  nothing works.
- `make contracts` regenerates three files together
  (`domain-schema.json`, `openapi.json`, `worldsim.ts`). The Vue client
  types come from `@gen`, so backend schema changes require a regen
  before the frontend typechecks.
- Never edit a landed migration. Event-type additions need a check
  constraint migration (`ck_event_type`) plus the matching model edit.
- The row/store version lockstep is load-bearing: any write that
  bypasses canonical must re-sync the version store or later touches
  409. Proven by `test_s5_focus.py`, not by inspection.
- Tests use the `migrated_db` scratch fixture and one event loop per
  test (engines created inside `_inner`, never shared across loops).
  FakeGateway routes key actors off the `>>(Name).` identity card line,
  never substring sniffing. Assign `gateway.route` explicitly or every
  call fails.
- `verify.mjs` needs a fresh database. A used DB fails with 409s that
  look like product bugs but are reseed state. Reset, migrate, rerun.
- Long-running dev processes live under `hub` (`api8100`, `vite5174`).
  A stale vite process serves stale overlays; restart it before
  trusting the browser.
- `.env` is never committed. `evidence/` bundles stay local except
  `stage3-live-v1`. `backups/` is gitignored.
- Auth model: key set means every non-probe request needs the bearer
  header, including tests that set the key env for other reasons
  (the S0 foundation client sends it). Compose `api` binds publicly,
  so it refuses to start keyless.
- One commit per task packet, named like the work (`S5 macro: ...`).
  Full suite plus `verify.mjs` before stage-close commits.
