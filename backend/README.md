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

## Stage 1 scene contracts (S1-CONTRACT-001)

Intent, Attempt, Reaction, Scene, Resolution in `src/worldsim/domain/scenes.py`,
`NarrationBeat` in `src/worldsim/domain/narration.py`, plus `CommunicateAction`
in the intent union (Stage 0 planning/validation reject non-Stage-0 families
loudly). Lifecycle enums in `domain/enums.py`; scene transition map
`PROPOSED -> VALIDATING -> READY -> RESOLVING -> RESOLVED -> COMMITTED`
(invalid/terminal branches included). Tables in migration
`0004_stage1_scenes` (one intent per character per snapshot; one attempt
per intent; one reaction per reactor per attempt; one resolution per
scene). Adapters and ports arrive with the owning consumer tasks.

## Stage 1 context, perception, graphs (S1-CTX-001, S1-PERCEPT-001, S1-GRAPH-001)

- Context (`domain/context.py`, `application/context/assembler.py`): typed
  request, fixed section order, owner/visibility filtering before ranking,
  deterministic per-section budgets with truncation markers, untrusted
  delimiters, rendered SHA-256 hash, include/exclude manifest sources.
- Perception (`domain/perception.py`, `domain/rules/perception.py`):
  participant sees all non-concealed facts; same-location observers see
  public/scene facts; absent characters see nothing; concealed facts reach
  only explicit disclosure recipients; phrasing outside the permitted set
  fails loudly.
- Graphs (`application/graphs/`): typed invocation/state, task-run UUID as
  thread ID, PostgreSQL checkpointer in the `graph_state` schema (migration
  `0005_graph_checkpoints`; tables created by saver setup), resume by
  re-invoking the same thread, prune helper for completed threads, and no
  repository write tools. Windows dev note: psycopg async needs a selector
  event loop (see `test_graph_runtime._run`).

## Stage 1 character decisions (S1-CHAR-001)

`application/graphs/character.py`: validate invocation, render prompt,
call model, validate schema, permission/knowledge precheck, one repair,
WAIT fallback. Role prompt is a versioned file (`prompts/`, only the
response-schema placeholder is filled). `CompletionRequest.system` keeps
role instructions in the provider-native system message: chat templates
(Tekken, Llama 3, etc.) are applied server-side by OpenAI-compatible
providers, so no per-model template config exists. Character fake profile
`character@decision-fake-v1`; the live path reuses `openrouter@chat-v1`.

## Stage 1 scenes and reactions (S1-SCENE-001, S1-REACT-001)

`domain/rules/scenes.py`: union-find over same target, same route,
activity-gated co-presence, move-to-someone meeting, mutual appointment,
shared desired effect, and `depends_on_intent_id` causal links (new
optional `DesiredEffect` field). Passive waits/rests at one location stay
apart. Deterministic UUID5 scene IDs, initiator/reactor participants,
sorted mutable aggregates, `scenes_overlap` for the commit stage.
`application/graphs/reaction.py` plus `prompts/reaction.v1.md` and profile
`reaction@react-fake-v1`: eligibility (not own attempt, alive, beats left,
participant or same location) runs before any model call; repair only when
beats allow two calls; fallback is no-reaction, never a wait.

## Stage 1 hybrid resolution (S1-RESOLVE-001)

`domain/rules/resolution.py`: per-intent feasibility envelopes over the
live view (stale sealed versions fail, infeasible is impossible, wait /
rest / observe / valid move resolve automatically with planned effects,
dialogue stays ambiguous). `merge_determined` takes the worst outcome.
`application/graphs/resolve.py` plus `prompts/resolver.v1.md` and profile
`resolver@resolve-fake-v1`: model proposals are validated against the
envelope (allowed outcomes, feasible effect types, aggregates matched by
raw identity since canon keys carry kind prefixes), repaired once, else
deterministic fallback. Resolutions carry a deterministic UUID5 seed.

## Stage 1 atomic scene commit (S1-COMMIT-001)

`CommitRequest.scene_records` extends the Stage 0 transaction: intent,
scene, attempt, reaction, and resolution rows persist in the same commit
as the event, with commit-time statuses and an `after_scene` rollback
hook. `transactions/scenes.py` builds the commit (`commit_scene`
command, `scene:{id}` idempotency, `narrate_scene` outbox as the only
pre-narration work) and converts permitted fact sets to observations.
Projections now fold effects per aggregate before saving once: per-effect
saves went stale on the second touch of one aggregate. New
`SceneRepository` port plus SQL adapter, wired into the unit of work.

## Stage 1 post-commit narration (S1-NARRATE-001)

`application/graphs/narrate.py` plus `prompts/narrator.v1.md` and profile
`narrator@narrate-fake-v1`: gating refuses uncommitted events before any
model call; beats validate cited fact keys against the visible set,
speakers against the audience, and count against the beat budget, with one
repair and a structured-event fallback that cites only visible facts.
`NarrationBeat.cited_fact_keys` (new column via `0006`) persists the audit
trail; `save_narration`/`narrations_for_event` round-trip beats without
touching projections. LangGraph drops undeclared state keys, so every
graph input used past entry must be a declared state field.

## Stage 1 orchestration (S1-ORCH-001)

`application/orchestration/stage1.py`: seal, concurrent decisions,
assemble, sequential react/resolve/commit/narrate per scene. Run states
reuse the existing lifecycle through `COMPLETED`; restarts replay via
content-addressed IDs (`derive_*` in `domain/ids.py`) and idempotent
command keys. Resolution versions pin to the live view at resolve time,
commits check only touched aggregates. Decisions assemble real context
(card, place, state, observations, memories) and audit every model call
through `TracedGateway` (manifest = assembler sources). Probe gate stops
the batch before the tick on provider outage; narration failures record
without failing the phase; player intents substitute with precheck.
Task-run rows are intentionally not written (recovery via idempotent
commits). Pause/resume flips run state; resume replays idempotently.

## Stage 1 command and read boundaries (S1-API-001)

`interfaces/http/routes/stage1.py`: watcher vs player perspective via
`X-Worldsim-Role` (`X-Worldsim-Character` for players). Character, scene,
and narration reads; player views show only participating scenes with
other authors' intent details stripped, and model runs stay
watcher-only. Advance (with player substitution limited to self),
pause, and resume commands reuse orchestrator idempotency, so repeats
return stored reports. Event cursor paging continues on `/world/events`.
`scripts/gen_ts_client.py` generates `content/clients/worldsim.ts` from
the OpenAPI contract (`make contracts`; drift fails the client test).

## Stage 1 Vue surface (S1-UI-001, direction B)

`frontend/` (Vue 3 + Vite + strict TS): stage view with scene strip,
beats, cast, phase status, role routing (watcher/player headers),
player action form with family-appropriate fields, busy-guarded submits,
retry with backoff, keyboard nav (arrows + slash), true black/white
themes, reduced-motion CSS. Imports `content/clients/worldsim.ts` by
alias, so client drift breaks the build. No canonical logic in TS:
rendering and submission only. Verify with `node verify.mjs` against a
running backend (headless Chromium: seed, advance, beats, action,
keyboard, theme, mobile, clean console).

## Stage 1 scenario and review gate (S1-GATE-001)

`tests/test_stage1_gate.py` drives the §2 fixture through the HTTP
boundary with scripted fakes and writes
`evidence/stage1-three-phase-v1/` (scenario, audit, performance, trace,
security, index, plus `REPORT.md` with the frozen handoff and honest
gaps). The fault matrix routes every failure taxonomy entry at every
role through a full advance; the live-provider scenario stays opt-in
behind `WORLDSIM_LIVE_SCENARIO=1`. Run with `make stage1-scenario`.

## D&D rules engine (DND-PORT)

`domain/rules/dnd/` is a deterministic port of `perchance-ver/dnd.js`
over the vendored SRD 5.1 tables in `content/dnd/` (provenance in
`content/dnd/README.md`). Dice, sheets, spells, monsters, combat,
encounter budgets, and narrator tag parsers. Rolls take an injected
`rng` callable and are reproducible with `random.Random(seed)`.
`tests/test_dnd_parity.py` pins all 39 behavior groups against vectors
generated from the monolith (`fixtures/dnd_vectors.json`, via
`node backend/scripts/gen_dnd_vectors.mjs`). Two monolith bugs are
fixed, not ported: crit damage (crashed on undefined `critDice`;
now double dice) and heal descriptions (`heals undefined`; now
resolved from the slot table). The missing-armor-skips-Dex quirk is
kept and pinned.

## D&D wiring (DND-WIRE, Wire-1)

Party roster persists in `dnd_party_member` (migration 0008) with a
slug `name_key` unique per world, version-guarded sheet saves, and the
4-member cap. `application/commands/party.py` seats the player
(`begin_adventure`) and resolves `RECRUIT[Name]: desc` tags
(`recruit_companion`, idempotent replays). Narration carries the party
block plus DM rules (`prompts/dnd-rules.v1.md`) when a roster exists,
sheets ride visible facts (`dnd-sheet:<name>`) and manifest sources,
and narrator output is scanned for recruits after every scene.
`POST /stage1/party/begin` and `GET /stage1/party` expose the roster;
narrator calls now set `phase_run_id` so the per-phase audit chain
covers them. Combat tag resolution (Wire-2) is still open.

## D&D combat resolution (DND-WIRE, Wire-2)

`domain/rules/dnd/combat_resolve.py` is a pure resolver: narration text
plus roster sheets plus tables plus one RNG stream in, rolls/HP
deltas/conditions/beats out. Attackers match by loadout, party targets
by name, others fall back to the monster tables with ephemeral HP.
Saves use class saving throws or precomputed monster bonuses; half
damage rounds down; heal `MOD` substitutes the caster's ability mod.
The orchestrator seeds the stream from the narrated event (63-bit
mask), persists HP/conditions through version-guarded saves, and
records one `ACTION_RESOLVED` world event (seed, algorithm, roll log)
plus deterministic outcome beats. Combat event IDs derive from the
source event, so a double resolve collides instead of double-applying.
Migration 0009 widens `world_event.random_seed` to 64-bit.

## D&D monster pools (DND-MONSTER)

`dnd_monster` (migration 0010) keeps one live HP pool per world and
monster key. The resolver takes live pools in and returns the touched
ones out; the applier upserts them through version-guarded saves in
the same retry loop as party HP. A fresh ENCOUNTER respawns its keys
to full (a new pack, not the survivors); scenes without one continue
the persisted HP, including across scenes. No XP awards yet.

## Visual assets (IMG-FIXTURE)

`content/visual-styles/pixel-saga-v1.json` is the versioned style
pack: portrait/sprite/background/event prompts, palette, continuity
rules, and the staged pipeline (fixture now, provider gateway in
Stage 3, ComfyUI in Stage 4). The Vue surface draws deterministic
16x16 SVG portraits from the pack palette (`frontend/src/portrait.ts`,
`Portrait.vue`); `portraitFor` is the seam the gateway replaces.
No backend surface: fixtures need none.

## Daily summaries (S2-SUMMARY-001)

After each midnight commit the orchestrator records one versioned
summary per owner with same-day sources (migration 0017).
Proposals cite only input source IDs; unknown citations, outages,
and malformed output fall back to structural counts. Versions
accumulate per (world, owner, day); raw observations and memories
are never touched, and summary failures never fail the phase.

## Roles (S2-ROLE-001)

One active grant per world selects the operating role at safe
boundaries (never mid-run); player grants bind a character. The
grant governs every caller, falling back to request headers only
where no grant exists. Director users propose through the same
validation as model proposals; deity patches one character per
audited canonical commit (`deity_override` event), with retcon
overrides additionally enqueueing a consistency-audit message.
Player-scoped reads stay header-bound as in Stage 1.

## Director (S2-DIRECTOR-001)

`narrative_hook` and `narrative_arc` rows hold opportunities, never
outcomes (migration 0016). Each advance runs the Director phase
after the seal: a deterministic cooldown trigger (world config,
default 3 phases) decides whether the model runs at all, and a
bounded proposal graph validates privileges (only `spawn_npc` and
`new_location` may be requested) and budgets (3 hooks, 2 arcs).
Rejections, no-ops, and outages all set `DIRECTOR_COMPLETE` and
let the phase continue; only runs advance the cooldown, so outages
retry next phase. The trigger check lives in the orchestrator
because graphs never touch repositories.

## Stage 2 contracts (S2-CONTRACT-001a)

`activity` tracks persistent undertakings (travel, rest, train,
work) with phase-counted progress and version-guarded saves;
`travel_route` stores world leg facts (duration, stamina) with one
leg per origin-destination pair. Party members carry an explicit
`focus_slot` (two mains, two subs, rest companions by seat order,
backfilled by name order). Product decision 2026-09-16, recorded in
the charter: the D&D HP engine is canonical; injuries arrive later
as a complement.

## Knowledge (S2-KNOW-001)

`claim` rows record voiced propositions with audience and optional
refutation links; `belief` rows fold per-holder confidence with
provenance (migration 0014). Hearing is positional: co-located
living characters form beliefs (speaker 0.9, first hearing 0.5,
repeats reinforce to 0.9), contradiction halves toward doubt, and
nothing is ever deleted. False claims touch no canon rows or
events. Reads filter claims by what the viewer could hear;
beliefs are holder- or watcher-only.

## Inventory and skills (S2-PROGRESS-001)

Item definitions are content (`content/definitions/items.json`);
`item_instance` rows carry the single holder, moved version-guarded
through audited give/transfer commands. Training sessions award
diminishing progress (8, 7, ... floor 1, cap 100) through a
`skill_progress` canonical effect: the same session key never
counts twice, stamina spends atomically alongside, and the resolver
allowlist excludes the effect so prose cannot award progression.
Tables arrive in migration 0015.

## Relationships (S2-REL-001)

`relationship_evidence` stores sourced directional deltas;
`relationship` folds trust/affection/respect per ordered pair with
clamped totals (migration 0013). Recording validates both ends,
audits the command, and folds in one transaction; scene replays
pass their event ID, adhoc calls mint a fresh key. Reads label
incoming vs outgoing, and decision context carries only the
actor's own outgoing rows (incoming rows are manifest-excluded).
Narration emits beats, never evidence.

## Activities (S2-ACTIVITY-001)

`POST /stage2/activities` starts one activity per character (travel
resolves its leg first); interrupt bakes progress, resume restarts
from the current phase, cancel is terminal, and repeats are no-ops.
The tick completes due activities with one canonical commit each:
travel moves and spends stamina (exhaustion stalls instead), rest
recovers, patrol observes, train/work record evidence in the event
summary. Progress derives from the clock, so quiet phases advance
activities with no writes and no model calls.

## Phase tick (S2-TIME-001)

Advancing refuses a new phase while the prior run is incomplete and
always fires due schedules, even on a resumed tick: each due row
records one `schedule_fired` event and flips to applied, so retries
never double-fire. `is_quiet_phase` (empty or all WAIT) marks the
phase report and API response; the client labels quiet scenes.
`scheduled_effect` arrives in migration 0012 alongside the widened
event-type check.

## D&D surface reads (DND-Surface)

`GET /api/v1/stage1/party` and `POST /api/v1/stage1/party/begin` project
`hp_current`, `hp_max`, and `conditions` per member, so the client can
render combat state without touching sheets. The generated TypeScript
client (`content/clients/worldsim.ts`) covers the party views and
routes. Static direction mocks live in `mocks/stage1/`: A/B for the
visual-novel timeline, C for the party roster plus combat log, D for
the narrow begin-adventure flow.
