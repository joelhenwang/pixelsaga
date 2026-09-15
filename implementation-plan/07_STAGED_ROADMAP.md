# Staged Roadmap

**Status:** Normative delivery sequence

## 1. Delivery strategy

Build the smallest complete causal loop at each stage. A stage is promoted only through an executable scenario and fault gate. Later-stage infrastructure must not enter earlier stages unless it removes an immediate risk and participates in the current proof.

```text
Stage 0: deterministic durable world kernel
   -> Stage 1: first bounded autonomous character/scene loop
      -> Stage 2: seven-day playable visual-novel world
         -> Stage 3: thirty-day memory, rules, quality, and image proof
            -> Stage 4: local model/image worker topology
               -> Stage 5: macro simulation and generations
```

## 2. Stage 0: deterministic foundation

### Stage 0 outcome

A seeded world executes and persists deterministic phase primitives, typed effects, events, observations, recent memories, tasks, and outbox messages with no external model dependency and full restart/idempotency safety.

### Stage 0 includes

- repository/configuration/test foundation;
- strict domain contracts;
- PostgreSQL/Alembic and minimal core schema;
- deterministic clock, RNG, simple `WAIT`, `REST`, `OBSERVE`, and `MOVE`;
- atomic event/effect/projection transaction;
- task leases, retry, idempotency, and outbox primitives;
- seed import;
- model gateway contract, fake adapter, optional OpenRouter probe;
- context manifest/model-call audit skeleton;
- minimal health/read/advance API and CLI;
- fault-injected deterministic scenario.

### Stage 0 excludes

Production LangGraph character behavior, Director, interactive scenes, long-term retrieval, combat, images, and production Vue UI.

### Stage 0 proof

Seed, advance, crash after commit before acknowledgement, restart, retry, and prove one event/effect result with correct observation and recent-memory provenance.

Detailed tasks: [08_STAGE_0_EXECUTION.md](08_STAGE_0_EXECUTION.md).

## 3. Stage 1: first autonomous vertical slice

### Stage 1 outcome

Two characters complete three selected phases from one sealed snapshot, including one interaction scene, differing perspectives, bounded LangGraph decisions, atomic resolution, post-commit narration, and restart recovery.

### Stage 1 includes

- perspective-safe Context Assembler;
- CharacterDecisionGraph and bounded repair/fallback;
- deterministic Scene Assembler;
- ReactionGraph where needed;
- minimal hybrid ResolutionGraph;
- atomic scene commit;
- perception and immediate memory;
- NarrationGraph after commit;
- thin timeline/visual-novel Vue surface near stage end;
- automatic/manual/player-controlled phase operation.

### Stage 1 excludes

Full ten-phase days, four-character cast, Director arcs, long-term vector retrieval, complex combat/magic, generated images, and public sharing.

### Stage 1 proof

Two characters act from the same snapshot; one secret remains isolated; one scene resolves; narration reflects but does not alter canon; duplicate task and restart produce no duplicate event.

Detailed tasks: [09_STAGE_1_EXECUTION.md](09_STAGE_1_EXECUTION.md).

## 4. Stage 2: seven-day playable world

### Stage 2 outcome

Four focus characters complete seven detailed days across all ten phases with persistent activities, restrained Director behavior, relationships, claims/beliefs, richer player control, and a usable visual-novel client.

### Stage 2 includes

- all ten phases and phase scheduling;
- two main and two sub-main focus slots;
- travel and persistent activities;
- goals and multi-phase plans;
- directional relationships;
- claims and bounded belief updates;
- Director trigger/proposal graph, hooks, pacing, and cooldowns;
- inventory/resources and evidence-based skill progress;
- role switching and Deity audit path;
- map, character, diary, operations, and timeline UI;
- deterministic/manual visual assets for UI continuity;
- daily summary proposal pipeline without vector decisions.

### Stage 2 proof

Seven days complete after injected process/model failures; quiet phases remain common; the Director does not fire every phase; perspectives and directional relationships differ; player and deity actions are correctly constrained/audited.

## 5. Stage 3: month-capable product proof

### Stage 3 outcome

Thirty autonomous days complete with long-term perspective-safe retrieval, bounded fantasy conflict and magic, measurable narrative quality, asynchronous image generation, and zero hard consistency violations.

### Stage 3 includes

- recent/long-term memory promotion and compaction;
- pgvector embeddings with exact filtered search;
- hybrid retrieval scoring and evaluation;
- richer scenes, combat, injuries, conditions, magic, and recovery;
- narrative arcs and trope/repetition controls;
- remote provider-neutral image gateway;
- visual state versions, reusable assets, and salient event images;
- encyclopedia, gallery, and richer map/timeline projections;
- evaluation datasets and 30-day soak harness;
- separated API/worker processes if operationally useful.

### Stage 3 proof targets

- zero hard invariant violations;
- zero seeded secret leaks;
- zero duplicate canonical effects;
- complete projection source links;
- at least 95% structurally valid state-affecting model responses after one repair;
- at least 90% recall of seeded important promises/discoveries in evaluation scenarios;
- bounded unsupported-memory and narration claims;
- distinct voices and decisions;
- no uncontrolled NPC/trope explosion;
- image backlog does not block simulation.

## 6. Stage 4: local inference and image topology

### Stage 4 outcome

The month-capable system runs against interchangeable local text/embedding workers and local ComfyUI without changing character identity, domain logic, or canon.

### Stage 4 includes

- capability benchmark and approved local model profiles;
- two compatible text-worker targets when hardware permits;
- local embedding adapter and versioned re-embedding;
- ComfyUI workflow and object-store adapter;
- model/image worker failover and health;
- request routing, backpressure, and resource budgets;
- optional Temporal adapter only if promotion criteria are met.

### Stage 4 proof

Run the same evaluation subset through remote and local profiles; kill a worker during work; recover through compatible retry/failover; preserve traceability, identity, and canonical outcomes. Image outage leaves text simulation healthy.

## 7. Stage 5: macro simulation and generations

### Stage 5 outcome

The world advances through quiet months/years and reaches a generation transition without simulating every detailed phase or losing genealogy, public history, character agency, or high-salience events.

### Stage 5 includes

- adaptive day/week/month/year resolution;
- macro activity, faction, economy, relationship, health, and ageing updates;
- salience interruption back to detailed mode;
- genealogy and lineage characters;
- focus-slot succession;
- era and autobiographical summaries with provenance;
- peace, eradication, and maximum-day end conditions;
- consistency checks across resolution changes.

### Stage 5 proof

A compressed multi-year fixture reaches one generation transition, preserves sourced public history, does not transfer private memories without lore, returns to detailed mode for a seeded major event, and evaluates configured ending conditions.

## 8. Cross-stage dependency graph

```text
S0 contracts/database/fakes
 -> S0 atomic commit/tasks/seed
 -> S0 deterministic runner and fault gate
 -> S1 context/perception/character graphs
 -> S1 scene assembly/resolution/commit
 -> S1 narration/UI and three-phase gate
 -> S2 full clock/activities/four characters
 -> S2 Director/relationships/claims/UI
 -> S2 seven-day gate
 -> S3 memory retrieval/rules/images/evaluations
 -> S3 thirty-day gate
 -> S4 local adapters/workers/failover
 -> S4 topology gate
 -> S5 macro/genealogy/endings
 -> S5 generation gate
```

## 9. Promotion rules

Before starting the next stage:

- all current-stage task acceptance criteria pass;
- hard gate runs from a clean environment;
- migrations upgrade from an empty database and prior promoted fixture;
- seed import remains idempotent;
- architecture fitness checks pass;
- fault scenarios produce no duplicate or partial canon;
- required evidence bundle is retained;
- active schema, seed, API, prompt, model-profile, and evaluation versions are frozen;
- known non-hard failures are documented with owner and stage;
- no hard invariant is waived silently.

## 10. Evidence bundle

Each stage stores:

- application and dependency versions;
- migration head and schema dump;
- seed and prompt/profile versions;
- generated JSON Schema and OpenAPI;
- deterministic scenario inputs and outputs;
- test/fault/evaluation reports;
- trace IDs or exported local traces;
- consistency audit;
- performance breakdown;
- security/redaction check;
- known limitations and next-stage handoff.

## 11. Promotion criteria for deferred infrastructure

| Infrastructure | Introduce only when |
| --- | --- |
| Approximate vector index | Exact filtered search misses measured latency target at realistic volume |
| Separate API/worker process | Long model/image work harms API responsiveness or failure isolation |
| Object storage | Asset volume/lifecycle exceeds verified local filesystem handling |
| Temporal | Database task/lease orchestration fails Stage 3 reliability or workflow complexity criteria |
| Redis | A measured coordination/cache need cannot be met safely through PostgreSQL/process memory |
| Multiple model workers | Local throughput or failover stage requires them |
| Public service/multi-user auth | Explicit product scope is approved |
| 5e rules mode | Product decision, licensing review, and separate rules schema are approved |

## 12. Rollback and compatibility

This is greenfield work, so rollback means returning to the previous promoted application/schema/seed version, not restoring PixelSaga behavior.

- Every migration has tested downgrade or documented forward-fix-only recovery.
- Before promotion, back up the prior fixture and verify restore.
- Model/prompt profile changes are versioned and selectable for evaluation.
- A new projection may shadow-read before replacing an old read path, but canonical writes remain single-owner.
- A failed stage does not mutate the prior promoted evidence fixture.
- Content/schema imports reject unsupported future versions rather than guessing.

## 13. Critical path

The critical path is:

```text
Domain contracts
 -> PostgreSQL transaction semantics
 -> idempotent event/effect commit
 -> sealed snapshot
 -> perspective-safe context
 -> bounded character proposal
 -> scene resolution
 -> atomic scene commit
 -> observations
 -> post-commit narration
 -> visual-novel projection
```

Do not prioritize broad content generation, image polish, or sophisticated agents ahead of this path.