# Testing and Evaluation Plan

**Status:** Normative verification strategy

## 1. Principle

Tests protect observable behavior, boundaries, invariants, and failure semantics. They do not exist to inflate coverage or pin implementation trivia.

A permanent test earns its place when a plausible bug would violate a product contract. Use a throwaway smoke scenario for wiring that does not justify permanent maintenance.

## 2. Verification layers

| Layer | Purpose | Typical mechanism |
| --- | --- | --- |
| Domain unit | Pure values, transitions, rules, effect validation | Pytest examples |
| Property/state machine | Broad invariant spaces and transition sequences | Hypothesis where valuable |
| Persistence integration | Constraints, transactions, concurrency, migrations | Real PostgreSQL fixture |
| Application integration | Commands, idempotency, orchestration, perspective | Real DB plus fakes |
| Graph/model contract | Structured proposals, repair, fallback, context | Scripted fake model and LangGraph checkpointer |
| Scenario/fault | End-to-end stage behavior and restart boundaries | Stage harness with fault injection |
| API contract | Stable DTO/error/idempotency/cursor behavior | FastAPI client against real services |
| Frontend unit | Complex local view behavior only | Vitest |
| UI behavior | User workflows and accessibility | Playwright against actual app |
| LLM evaluation | Subjective quality and retrieval/model behavior | Versioned local datasets, optional LangSmith experiments |
| Soak/consistency | Long-running growth, recovery, invariants | Seeded 7/30-day harness |

## 3. Test design rules

- Use deterministic operational clock and RNG.
- Default tests make no external network requests.
- Use a real PostgreSQL instance for transaction, lock, migration, and constraint behavior.
- Test public/domain behavior, not private call counts unless the count is a cost or safety contract.
- Do not mock the unit under test.
- Do not assert raw prose wording except for explicit content/safety fixtures.
- Do not snapshot giant JSON payloads without a focused semantic reason.
- Avoid duplicated parameter rows that exercise the same branch.
- A retry test must prove one logical result, not merely that no exception occurred.
- A perspective test must assert forbidden source absence, not only expected source presence.
- A transaction test must inspect all relevant rows after injected failure.
- Keep live-provider tests opt-in, capped, and excluded from promotion gates unless a stage explicitly says otherwise.

## 4. Deterministic scenario harness

The harness controls:

- seed/content version;
- operational and fictional clocks;
- random seed stream and algorithm version;
- model responses, latency, malformed output, refusal, timeout, and rate limits;
- graph interruption points;
- task lease owner/expiry;
- database fault boundaries;
- image/embedding availability;
- expected canonical event/effect sequence;
- expected perspective source IDs;
- call/token/task budgets.

A scenario output includes canonical timeline, projection hashes, observations, memories, task/model traces, retry history, outbox state, and consistency report.

## 5. Fixture catalogue

Maintain small versioned fixtures:

- empty database and each promoted-stage database;
- minimal valid/broken seed;
- two-character secret-isolation world;
- same-snapshot interacting intents;
- compatible and conflicting scenes;
- false claim and divergent belief;
- activity interruption and travel conflict;
- duplicate command/task delivery;
- crash before commit and after commit/before acknowledgement;
- malformed/refused/timed-out/rate-limited model results;
- unsupported narration fact;
- important memory/distractor retrieval set;
- combat success/partial/failure/retreat/death;
- valid/invalid magic use;
- image hallucination/backlog/failure;
- hard-retcon taint scenario;
- macro-simulation salience interruption;
- generation succession and private-memory noninheritance.

Fixtures use synthetic fictional data only.

## 6. Hard invariant suite

Continuously audit:

- event sequence and aggregate versions are monotonic;
- one logical result per idempotency key/input hash;
- every effect belongs to one event with unique ordinal;
- every projection change has source event/version;
- sealed snapshots never change;
- all same-phase primary intents use one snapshot;
- required phase scenes are terminal before phase completion;
- no phase follows a partially canonical phase;
- entity and unique-item ownership/location are singular;
- resources remain in rule bounds;
- observation facts are subsets of permitted fact sets;
- memory owner/visibility/provenance exists;
- model and narration records cannot mutate canon;
- images do not affect phase completion;
- task lease and terminal-state rules hold;
- no remote call occurs inside a canonical DB transaction;
- graph checkpoint removal does not alter canon.

Any hard invariant failure blocks promotion.

## 7. Fault-injection matrix

Inject failure:

- before task claim;
- after claim/before execution;
- during model request;
- after model response/before proposal persistence;
- after proposal/before validation;
- after validation/before transaction;
- after each event/effect/projection/observation/outbox insert;
- immediately before commit;
- after commit/before acknowledgement;
- during narration, embedding, image, and projection workers;
- during lease heartbeat;
- during WebSocket delivery;
- during export/restore promotion;
- during phase and macro-period transitions.

For each boundary define expected retry owner, idempotency lookup, terminal status, user-visible state, and allowed canonical row changes.

## 8. Concurrency tests

Use a real database to prove:

- two phase leaders cannot own one world;
- two workers cannot claim one unexpired task;
- expired tasks may be reclaimed;
- late prior owners cannot overwrite terminal task state;
- stale scene resolutions cannot both commit;
- disjoint scenes can commit independently;
- shared aggregate scenes conflict deterministically;
- duplicate outbox delivery creates one logical asset/memory/projection result;
- event cursors remain strictly ordered.

## 9. Migration tests

Every migration change runs:

1. upgrade empty database to head;
2. upgrade every supported promoted-stage fixture to head;
3. validate constraints and row counts;
4. run consistency audit;
5. downgrade/re-upgrade where downgrade is supported;
6. verify one Alembic head;
7. generate and compare intended schema artifact.

Destructive transformations require a backup, restore proof, and explicit forward-fix plan.

## 10. Context and perspective tests

For each model role:

- exact allowed source classes;
- owner and visibility SQL filters;
- as-of snapshot/event sequence;
- deterministic ranking and section budgets;
- untrusted-content delimiters;
- context manifest completeness;
- absence of seeded secrets;
- tool scope and output limits;
- prompt-injection fixtures in lore, memory, dialogue, and user text.

Test that adversarial content remains quoted data and cannot expand tools, permissions, source scope, or output effect vocabulary.

## 11. Evaluation datasets

Local, version-controlled JSON/JSONL fixtures are the source of truth. LangSmith datasets may mirror them for experiments but are not required to run core evaluation.

### `character-decision-vN` (`single_step`)

Inputs: Context Envelope, role/profile/prompt versions.
Outputs: allowed intent families, forbidden knowledge/actions, optional reference characteristics.
Metrics: schema validity, knowledge compliance, capability support, goal relevance, voice distinctness, safe fallback.

### `director-proposal-vN` (`single_step`)

Inputs: pacing state, hooks, recent events, budgets.
Outputs: no-op eligibility, permitted proposal categories, forbidden forced outcomes.
Metrics: trigger appropriateness, agency preservation, prerequisite support, trope cooldown, NPC budget.

### `scene-resolution-vN` (`single_step`)

Inputs: attempts, reactions, feasible envelope, deterministic evidence.
Outputs: allowed outcome/effects.
Metrics: envelope compliance, causal support, fairness, effect validity, unsupported power-up rate.

### `narration-vN` (`final_response`)

Inputs: committed visible event packet and style profile.
Outputs: narration beats.
Metrics: fact support, perspective, character voice, readability, repetition, subtext, non-cringe style.

### `memory-retrieval-vN` (`rag`)

Inputs: owner, visibility, query/purpose, candidate corpus.
Outputs: expected source IDs and forbidden IDs.
Metrics: recall, precision, secret leakage, reciprocal rank, source diversity, latency, token cost.

### `graph-trajectory-vN` (`trajectory`)

Inputs: workflow invocation and scripted model behavior.
Outputs: allowed node/tool sequence and maximum repair count.
Metrics: trajectory validity, tool scope, bounded repair, fallback selection.

### `long-soak-quality-vN`

Inputs: fixed seed, profiles, budgets, days.
Outputs: expected hard invariants and quality ranges rather than exact prose.
Metrics: duplicate/leak counts, Director/trope/NPC growth, character distinctness, unresolved commitment recall, latency/cost.

## 12. Dataset lifecycle

1. Create a local schema and stable dataset/example IDs.
2. Run the actual graph or pipeline on representative inputs.
3. Inspect raw outputs and LangSmith/local traces before writing extraction or evaluators.
4. Normalize the run function output to the dataset schema.
5. Write deterministic evaluators first.
6. Test each evaluator against known good and bad examples.
7. Add one-metric LLM judges only for subjective qualities.
8. Run locally and review disagreements.
9. Optionally upload a versioned mirror to LangSmith.
10. Record dataset hash, evaluator versions, model profile, experiment ID, and results in the stage evidence bundle.

Never assume graph stream/output shape. Inspect it after implementation, including nested graph/tool events, before trajectory extraction.

## 13. Evaluator rules

Deterministic evaluators own:

- JSON/schema validity;
- ID membership and source coverage;
- visibility/secret leakage;
- effect-envelope compliance;
- duplicate counts;
- trajectory/tool constraints;
- budgets and latency;
- provenance links.

LLM-as-judge evaluators own subjective metrics such as voice, engagement, subtext, causality presentation, and trope quality. Each evaluator returns one metric and a concise reason.

Judges:

- use structured outputs;
- have versioned prompts/profiles;
- run asynchronously where useful;
- are evaluated on known good/bad anchors;
- never determine canon;
- do not receive hidden data unnecessary for the rubric;
- are not used when deterministic comparison is available.

## 14. LangSmith execution policy

- Use distinct projects for development, evaluation, and any opt-in production tracing.
- Attach dataset evaluators to explicit versioned datasets.
- Attach online evaluators only after offline validation.
- Match run-function output fields to dataset fields.
- Keep local evaluators with repository dependencies local; uploaded code evaluators must fit sandbox limitations.
- Inspect evaluator names/targets before replacement or deletion.
- Do not use destructive noninteractive CLI flags without explicit authorization.
- Retain local dataset and result summaries even when LangSmith is unavailable.

## 15. Narrative quality metrics

Hard deterministic:

- unsupported fact count;
- perspective violation count;
- forbidden content count;
- exact/near phrase repetition;
- Director intervention rate;
- new NPC rate;
- call/repair/fallback budgets.

Evaluated ranges:

- causal coherence;
- character voice distinctness;
- agency preservation;
- emotional subtext;
- romance reciprocity/pacing;
- villain/side-character dimensionality;
- consequence quality;
- exposition density;
- quiet-scene quality;
- engagement.

Quality gates use a combination of no-regression thresholds, minimum score floors, and human inspection. One aggregate judge score cannot hide a hard factual violation.

## 16. Frontend testing

Vitest is reserved for nontrivial state transitions and pure presentation logic. Playwright protects:

- role-aware navigation;
- automatic/manual/player control;
- visual-novel scene and timeline;
- stale/duplicate command behavior;
- reconnect and cursor replay;
- delayed/failed narration and images;
- desktop/mobile layout;
- keyboard and focus management;
- true dark/white and reduced motion;
- hidden information absence in player views.

Do not assert incidental CSS class names or pixel-perfect positions unless a visual regression workflow is explicitly adopted.

## 17. Performance and cost evidence

Measure separately:

- task queue wait;
- snapshot and context query time;
- retrieval time and candidate counts;
- model time/tokens by role/profile;
- repair/fallback rate;
- scene assembly/resolution;
- database transaction duration;
- observation/memory creation;
- narration/image latency;
- API projection and client render;
- idle CPU/RAM and worker resource usage.

Optimization follows measured bottlenecks. Model calls, context size, unnecessary agents, and image work receive priority over low-level control-plane rewrites.

## 18. Stage evidence report

Each promoted stage report includes:

- exact commands and environment profile;
- test and scenario results;
- migration and architecture results;
- fault matrix result;
- hard invariant audit;
- dataset/evaluator versions and hashes;
- model profiles and experiment IDs;
- performance/cost breakdown;
- security/redaction result;
- observed limitations;
- links from failures to traces and source records.

A failed check is reported as failed. Do not average or reword it into success.