# Stage 1 Execution Plan

**Stage ID:** `stage1-two-character-v1`
**Outcome:** Two characters complete three consecutive phases from shared snapshots with perspective-safe bounded LangGraph decisions, one interacting scene, atomic canon, differing observations, post-commit narration, and a thin visual-novel timeline.

## 1. Preconditions

- Stage 0 hard gate is promoted.
- Stage 0 schema, seed, transaction, idempotency, task, model gateway, and audit contracts are frozen.
- OpenRouter capability profile is available for opt-in live scenarios; fake models remain the default gate.

## 2. Scenario definition

Use two characters in connected locations across three consecutive phases. The fixture contains:

- distinct goals and voices;
- one private fact known only to character A;
- one public fact;
- one scheduled interaction opportunity;
- one conflicting or compatible pair of intents that forms a scene;
- deterministic WAIT fallback;
- a narration fixture with a deliberate unsupported-fact candidate.

All primary intents in each phase use the same sealed snapshot. Character B's context and outputs must never contain A's private fact unless a committed causal disclosure occurs.

## 3. Dependency order

```text
S1-CONTRACT-001
 -> S1-CTX-001 + S1-PERCEPT-001 + S1-GRAPH-001
 -> S1-CHAR-001
 -> S1-SCENE-001 + S1-REACT-001
 -> S1-RESOLVE-001
 -> S1-COMMIT-001
 -> S1-NARRATE-001
 -> S1-ORCH-001
 -> S1-API-001
 -> S1-UI-MOCK-001 -> product-owner selection -> S1-UI-001
 -> S1-GATE-001
```

## 4. Task packets

### S1-CONTRACT-001: intent, scene, reaction, resolution, and narration contracts

**Depends on:** Stage 0

**Deliver:**

- versioned `Intent`, `Attempt`, `Reaction`, `SceneProposal`, `Resolution`, and `NarrationBeat` schemas;
- stable action family and desired-effect representation;
- validation/repair/fallback errors;
- Stage 1 scene/task lifecycle additions;
- generated JSON Schema and migration for exercised records.

**Verify:** strict valid/invalid examples, unknown effect rejection, extra-field rejection, and schema round trips.

### S1-CTX-001: perspective-safe Context Assembler

**Depends on:** S1-CONTRACT-001

**Deliver:**

- typed context request/envelope/manifest contracts;
- structured queries for identity, perceived environment, own state, goals, known relationships, observations, recent memory, and local/public lore;
- owner/visibility filters before ranking;
- deterministic section budgets and truncation;
- untrusted-data delimiters;
- rendered-context hash and complete source manifest.

**Verify:** A and B contexts share snapshot ID, differ correctly by perspective, exclude the seeded secret from B, remain deterministic, and respect byte/token budgets.

### S1-PERCEPT-001: observation fact-set service

**Depends on:** S1-CONTRACT-001

**Deliver:** deterministic observer eligibility and permitted fact sets using participation, location, visibility, hearing, direct communication, and concealment fixtures.

**Verify:** participant, nearby observer, absent character, concealed action, and explicit disclosure cases. Optional phrasing cannot add a forbidden fact.

### S1-GRAPH-001: LangGraph runtime foundation

**Depends on:** S1-CONTRACT-001, Stage 0 task/model trace contracts

**Deliver:**

- typed graph invocation/runtime state;
- PostgreSQL checkpointer in a separate namespace;
- task-run UUID as thread ID;
- graph node tracing metadata;
- retention/pruning command;
- no repository write tool;
- restart from a model/validation boundary.

**Verify:** interrupted fake graph resumes once; completed checkpoint deletion leaves canon/audit intact; LangSmith disabled behavior is identical.

### S1-CHAR-001: CharacterDecisionGraph

**Depends on:** S1-CTX-001, S1-GRAPH-001

**Deliver:** bounded graph specified in [04_AI_CONTEXT_AND_TRACING.md](04_AI_CONTEXT_AND_TRACING.md), role prompt v1, model profile v1, structural validation, deterministic prechecks, one repair, and WAIT fallback.

**Verify:** valid intent, malformed response repaired, repeated malformed response falls back, timeout/rate limit safe behavior, impossible knowledge/target rejection, character voice fixture, and no cross-private data.

### S1-SCENE-001: deterministic Scene Assembler

**Depends on:** S1-CONTRACT-001, S1-CHAR-001

**Deliver:** grouping by target, location, route, appointment, shared resource, and causal dependency; disjoint mutable aggregate set detection; deterministic ordering; scene beat budgets.

**Verify:** compatible meeting, conflicting target, unrelated intents, shared unique item, and deterministic grouping independent of model completion order.

### S1-REACT-001: bounded ReactionGraph

**Depends on:** S1-CTX-001, S1-SCENE-001

**Deliver:** reaction eligibility, observable-attempt context, reaction schema/profile/prompt, one repair, deterministic no-reaction fallback, and beat-budget enforcement.

**Verify:** eligible target reacts from own perspective; absent/unaware target receives no call; initiator cannot author hidden reaction; call count stays inside budget.

### S1-RESOLVE-001: minimal hybrid ResolutionGraph

**Depends on:** S1-SCENE-001, S1-REACT-001

**Deliver:** deterministic feasibility envelope, automatically resolved cases, bounded ambiguity packet, resolver graph/profile, effect validation, deterministic fallback, seed/result evidence.

Stage 1 permits only effects supported by the current rules: movement, observation/disclosure, wait/rest, bounded resource changes, and simple activity state.

**Verify:** success, partial, failure, impossible, stale target, deterministic-only, ambiguous-model, malformed-model, and fallback cases.

### S1-COMMIT-001: atomic scene transaction

**Depends on:** S1-RESOLVE-001, S1-PERCEPT-001

**Deliver:** Stage 0 transaction extension for scene, intent, attempt, reaction, resolution, effects, observations, immediate memories, and narration outbox record.

**Verify:** one atomic scene result; rollback at each injected boundary; stale aggregate rejection; duplicate scene/task result; observations match allowed fact sets; narration work exists only after commit.

### S1-NARRATE-001: post-commit NarrationGraph

**Depends on:** S1-COMMIT-001, S1-GRAPH-001

**Deliver:** audience-scoped narration context, structured narration beats, narrator profile/prompt, unsupported-fact validator, one repair, and structured-event fallback.

**Verify:** narration starts after event commit, references only visible committed facts, cannot change projections, survives model outage, and exposes source event IDs.

### S1-ORCH-001: three-phase autonomous orchestration

**Depends on:** S1-CHAR-001, S1-SCENE-001, S1-RESOLVE-001, S1-COMMIT-001, S1-NARRATE-001

**Deliver:**

- automatic and manual advancement for three consecutive phases;
- concurrent primary character tasks after snapshot seal;
- barriers for scene assembly and required commits;
- player-supplied intent substitution for one controlled character;
- pause/resume/reconcile at safe boundaries;
- quota check before required model batch;
- phase completion independent of narration completion.

**Verify:** restart at snapshot, between two character completions, during resolution, after commit, and during narration; no duplicate or partial canon.

### S1-API-001: Stage 1 command and read boundaries

**Depends on:** S1-ORCH-001

**Deliver:** character/perspective/scene/narration/model-run/context-manifest read APIs; player intent, pause, and resume commands; event cursor updates; generated TypeScript client.

**Verify:** Watcher and player views differ; player route cannot access omniscient context; stale and duplicate commands have stable responses; reconnect resumes from cursor.

### S1-UI-MOCK-001: visual-novel static direction mocks

**Depends on:** S1-API-001 response fixtures

**Deliver:** at least two distinct standalone HTML/vanilla JavaScript mocks using realistic Stage 1 data. Cover timeline, current scene, dialogue/narration, participant portraits/placeholders, suggested/custom player action, phase status, and a narrow mobile layout.

Use true dark `#000` and true white modes, information-dense composition, minimal copy, no decorative card/pill default, and reduced motion.

**Acceptance:** product owner selects one direction. Stop before implementing Vue production components.

### S1-UI-001: thin Vue timeline and visual-novel surface

**Depends on:** explicit selection from S1-UI-MOCK-001

**Deliver:** Vue/Vite setup, generated API client, current world/phase status, timeline, scene beats, player action form, connection/retry state, role-safe routing, dark/white themes, keyboard and reduced-motion support.

**Verify:** actual browser against running API on desktop/mobile, keyboard-only path, delayed narration fallback, reconnect/cursor replay, duplicate-submit handling, and no canonical rule logic in TypeScript.

### S1-GATE-001: three-phase scenario and review

**Depends on:** all Stage 1 tasks

**Deliver:** fake-model deterministic scenario, opt-in capped live-provider scenario, fault matrix, perspective audit, architecture report, trace export/reference, performance breakdown, and evidence bundle.

## 5. Hard exit gate

All must pass:

- both primary intents in each phase reference one snapshot;
- contexts contain only permitted sources and B never receives A's seeded secret;
- model output cannot directly write a repository;
- at least one two-character scene is assembled independent of model completion order;
- valid reactions belong to the reacting participant;
- deterministic and model-assisted resolution stay inside feasible effects;
- event/effects/observations/immediate memories commit atomically;
- duplicate delivery and crash recovery create no duplicate canon;
- narration begins after commit and cannot alter state;
- narration failure uses structured fallback and does not block the next phase;
- player controls an attempt, not its outcome;
- fake path makes no network calls;
- live-provider scenario is optional, capped, and uses the same gateway contract;
- durable PostgreSQL audit connects phase, task, graph, context, model, resolution, event, and observations;
- LangSmith is optional and non-authoritative;
- Vue surface passes actual desktop/mobile/keyboard/reconnect verification;
- zero hard consistency and seeded-secret violations.

## 6. Performance evidence

Measure separately:

- snapshot sealing;
- context assembly and retrieval queries;
- queue wait per character;
- model latency and tokens per role;
- scene assembly;
- resolver latency;
- DB commit;
- observation creation;
- narration latency;
- API projection and client render.

Do not set aggressive optimization targets until this baseline exists. Record unexpected serial bottlenecks and unnecessary model calls.

## 7. Frozen handoff

Freeze:

- Stage 1 intent/scene/reaction/resolution/narration schemas;
- Context Envelope and Manifest v1;
- graph state/thread/checkpoint semantics;
- character, reaction, resolver, and narrator prompt/profile versions;
- perspective policy v1;
- scene commit interface;
- selected UI direction and tokens;
- three-phase scenario/evaluation fixtures;
- migration head and evidence bundle.