# Monolith Migration and Future-Proofing Reference

**Purpose:** concise handoff for the agent migrating the current single-file HTML LLM DnD Pixel Art RPG (`./perchance-ver`) into a maintainable, local-first application.

**Guiding principle:** future-proof the boundaries now; add future infrastructure only when the current stage requires it.

## 1. Starting point and target

The current application is a monolithic HTML app. Its exact globals, DOM coupling, storage format, prompts, and request flow must be inspected before changes are proposed. Do not assume the monolith is disposable: preserve its working behavior and visual identity while replacing it incrementally.

The intended near-term stack is:

| Area | Choice |
| --- | --- |
| Frontend | Svelte 5, TypeScript, Vite, scoped CSS |
| Backend and authoritative game engine | Python, FastAPI, Pydantic, `httpx`, `uv` |
| Persistence | SQLite, event history, periodic snapshots, JSON import/export |
| Retrieval | Structured queries and SQLite FTS5 first |
| LLM integration | Provider-independent, preferably OpenAI-compatible gateway |
| Streaming | SSE or fetch streaming; WebSockets only when bidirectional realtime is needed |
| Tests | `pytest`, Vitest, Playwright |
| Deployment | One FastAPI process/port serving the built frontend; private access through Tailscale Serve |

Python owns all canonical game state and rules. Svelte owns presentation state only, such as open panels, animation state, selected entities, and layout preferences.

## 2. Non-negotiable architecture rules

1. **One source of truth:** canonical game state lives in the Python backend and database, never simultaneously in browser globals and backend objects.
2. **LLMs propose; code decides:** model output is untrusted structured input. Pydantic validates its shape; deterministic rules validate permissions, knowledge, location, resources, targets, and current versions before effects are committed.
3. **Commit before presenting fact:** narration must not establish an outcome before its structured effects have been accepted and committed.
4. **Typed write path:** every mutation follows `Command -> Orchestrator/Application Service -> Validator/Resolver -> Effects/Events -> Transaction -> Projection`.
5. **Short transactions:** never perform LLM, embedding, image, or other remote calls inside a database transaction.
6. **Idempotent commands:** every state-changing request carries an idempotency key. A retry returns the original result rather than applying it twice.
7. **Perspective isolation:** players and NPCs receive only facts they could know. No agent gets arbitrary repository or omniscient database access.
8. **Framework-independent domain:** domain code must not import FastAPI, an ORM, LangGraph, model SDKs, or frontend code.
9. **Replaceable adapters:** persistence, model providers, retrieval, image generation, and later orchestration sit behind explicit ports.
10. **Version important contracts:** API DTOs, events, save files, prompts, model profiles, and context manifests need schema/version identifiers and migration paths.

## 3. Target request flow

```text
Player command
  -> FastAPI boundary validation
  -> application/game service
  -> snapshot + perspective-safe context
  -> deterministic logic and/or typed LLM proposal
  -> validator/resolver
  -> atomic event/effect/state commit
  -> narration and UI projection
  -> client update
```

The LLM must never be the database or state machine. Record deterministic dice seeds/results and all accepted effects so outcomes can be debugged and reproduced.

## 4. Code boundaries

```text
backend/src/rpg/
  domain/          pure entities, value objects, commands, events, rules
  application/     use cases, orchestration, context assembly, ports
  agents/          prompts and model-facing decision/narration workflows
  infrastructure/  SQLite repositories, LLM adapters, storage, telemetry
  interfaces/      FastAPI routes, DTOs, streaming, CLI

frontend/src/
  components/      dialogue, choices, character, inventory, combat, common
  state/           UI state only
  api/             generated or shared API client/types
  styles/          tokens, themes, layout
  assets/
```

Dependency direction is `interfaces/agents/infrastructure -> application -> domain`. Keep the authoritative engine in Python; do not build a second rules engine in TypeScript.

## 5. Incremental migration plan

### Phase 0 — freeze and map behavior

Before structural edits:

- inventory scripts, global variables, state mutations, DOM IDs/listeners, timers, prompts, provider calls, assets, local storage, save files, and user actions;
- document the current action-to-render path and identify canonical-versus-derived state;
- capture representative legacy saves and network/model fixtures;
- add a few Playwright characterization tests for new game, action/choice, save/load, settings, and failure recovery;
- record baseline startup, idle RAM/CPU, action latency, and first-token latency.

Deliver an inventory and dependency map before choosing extraction order. Preserve unknown behavior with tests rather than rewriting from memory.

### Phase 1 — introduce a backend seam

Create the FastAPI layered skeleton, health endpoint, configuration, fake model adapter, and typed request/response contracts. Keep the existing HTML UI working. Move provider credentials, LLM requests, prompt loading, and context construction out of the browser first.

The browser should call one stable API client; API handlers remain thin and call application services. Use a single Uvicorn worker for the local/small-user workload.

### Phase 2 — move authority by vertical slice

Define typed `GameState`, `GameCommand`, `GameEvent`, `Effect`, and `Resolution` contracts. Move one complete workflow at a time—such as player action, inventory, or combat—from browser mutation to Python validation and persistence.

During each cutover, shadow-compare old and new calculations when useful, but never allow two writers. Delete or disable the legacy writer once the backend becomes authoritative for that slice.

### Phase 3 — persistence and compatibility

Start with SQLite, not PostgreSQL. Store current state/projections plus an append-only event history and periodic snapshots; this is pragmatic event-oriented persistence, not pure event sourcing.

Provide:

- transactional commits with expected aggregate versions;
- legacy save import and validation;
- versioned JSON export/import;
- backup/restore tests;
- FTS5 over memories, lore, events, quests, notes, and conversations when needed.

Repository interfaces must make a later PostgreSQL adapter possible without changing domain rules. Do not add embeddings until entity/metadata filters, recency, importance, and FTS5 have a demonstrated recall gap.

### Phase 4 — replace the UI incrementally

Set up Svelte/Vite and migrate visible regions as components: dialogue, choices, character panel, inventory, combat, settings, map, and history. Components consume backend projections and submit typed commands; they do not infer or mutate canonical state.

Preserve existing CSS/assets where practical, then consolidate colors, spacing, typography, radii, and motion into design tokens. Finish when `index.html` is only the Vite entry shell. Add PWA support after the core migration is stable.

### Phase 5 — reliability and memory

Add a single Context Assembler that produces bounded, reproducible, perspective-safe envelopes containing identity, current scene, observations, relationships, goals, recent memory, retrieved memory, known lore, source IDs/hashes, and token budgets.

Put all model access behind a Model Gateway that maps logical roles—narrator, character, director, resolver, summarizer—to versioned profiles and handles capabilities, timeouts, retries, fallbacks, structured output, and usage records.

For streaming, prefer `POST /actions -> run_id` followed by `GET /runs/{run_id}/events` over SSE, or use a streamed `fetch` response. Add WebSockets only for multiplayer, spectators, synchronized combat, or truly server-initiated bidirectional interaction.

## 6. Minimal persistence/API shape

Initial tables should cover campaigns, current aggregate state, characters, events, snapshots, messages, prompt/model-call metadata, and idempotency records. Add normalized quest, inventory, relationship, location, or memory tables when their querying and integrity needs justify them; event payloads may remain versioned JSON.

Useful initial endpoints:

```text
POST /api/campaigns
GET  /api/campaigns/{id}
POST /api/campaigns/{id}/actions
GET  /api/runs/{id}/events
GET  /api/campaigns/{id}/events?after=<sequence>
POST /api/campaigns/{id}/export
POST /api/campaigns/import
GET  /api/models
GET  /api/settings
PUT  /api/settings
```

Use stable error codes, sequence cursors, optimistic versions, and explicit destructive-action confirmation.

## 7. Testing gates

Do not remove a legacy path until its replacement proves:

- characterization tests still pass;
- duplicate commands do not duplicate effects;
- malformed or disallowed model output cannot mutate state;
- model calls occur without an open database transaction;
- player/NPC contexts contain no forbidden private facts;
- save import/export round-trips across schema versions;
- a crash after commit returns the existing result on retry;
- the fake model and a live OpenAI-compatible provider use the same application contract;
- frontend components contain no game-rule implementation;
- idle and action-path resource/latency regressions remain within recorded budgets.

## 8. Defer until promotion criteria exist

Do not initially add PostgreSQL/pgvector, Redis, Temporal, microservices, multiple workers, object storage, ComfyUI, a generic agent framework, a global LangGraph thread, or a full WebSocket bus.

Promote only on evidence—for example, PostgreSQL for concurrent writers/operational needs; vectors for measured retrieval failures; background workers/outbox for durable non-blocking jobs; Temporal for workflows that outgrow database-backed state machines; PixiJS for a genuinely sprite-heavy canvas; WebSockets for bidirectional realtime.

The later architecture may distribute the control plane, Halo-hosted OpenAI-compatible model servers, embeddings, and image workers across machines. Character identity must remain data and must never be tied to a process or GPU, so workers can fail or move without changing the world.

## 9. Deployment direction

During development, Vite, FastAPI, and the model server may use separate ports. For normal use, build the Svelte frontend and let FastAPI serve it from one port, bound to `127.0.0.1`. Expose it privately with Tailscale Serve; avoid public binding and extra reverse proxies unless requirements change.

Keep the non-LLM stack quiet at idle. Optimization priority is model inference, prompt/context length, KV cache, retrieval quality, asset loading, and unnecessary model calls—not rewriting the control plane in a lower-level language.

## 10. First assignment for the new agent

Start with **Phase 0 only**. Inspect the repository and return:

1. a current-state inventory;
2. a diagram of the actual action, state, storage, and LLM flows;
3. the riskiest couplings and undocumented behavior;
4. proposed characterization tests and fixtures;
5. a vertical-slice migration order with rollback points;
6. discrepancies between this reference and the real code.

Do not begin the rewrite until that report is reviewed. Every later phase should be a small, reversible change that leaves the application runnable.

---

This reference adapts the broader `04_SYSTEM_ARCHITECTURE(1).md` design to the current monolith. Where they differ for the initial migration, this document intentionally chooses Svelte over Vue, SQLite over PostgreSQL, SSE/fetch streaming over WebSockets, and one process over distributed workers. The broader document remains the long-term reference for advanced simulation, transactional outbox, workers, PostgreSQL/pgvector, Temporal, and multi-machine operation.
