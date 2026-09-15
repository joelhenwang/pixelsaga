# AI, Context, LangGraph, and Tracing Design

**Status:** Normative model-system design

## 1. Principle

LangChain and LangGraph improve model integration, context control, resumable bounded workflows, and observability. They do not own the world scheduler, canon, domain memory, or database transactions.

```text
Application orchestrator owns when and why work runs.
Context Assembler owns what a model may know.
LangGraph owns bounded model/repair workflow state.
Model Gateway owns provider execution and usage records.
Application validators decide whether proposals are acceptable.
Canonical Transaction Service owns all state commits.
```

## 2. Logical model roles

| Role | Input scope | Output | Canonical authority |
| --- | --- | --- | --- |
| Character decision | One character perspective | Structured intent | None |
| Narrative Director | Omniscient but bounded world/pacing context | Event/hook/arc proposal or no-op | None |
| Semantic validator | Proposed intent/effect plus bounded relevant context | Concerns/classification | None |
| Hybrid resolver | Feasible outcome envelope and scene evidence | Structured resolution proposal | None |
| Reaction | One reacting participant's perspective and observable attempt | Structured reaction | None |
| Narrator | Committed event and audience-visible facts | Prose/visual-novel beats | None |
| Memory consolidator | One owner's sourced observations/memories | Summary/belief/memory proposals | None |
| Image prompt composer | Committed event plus versioned visual facts | Image specification/prompt | None |
| Evaluator | Trace/output and rubric | Scores/reasons | None |

A physical model may serve several logical roles through separate versioned profiles.

## 3. Model gateway

Application-facing protocol:

```text
complete(role, messages/context, response_schema, request_context) -> ModelResult
embed(role, texts, request_context) -> EmbeddingResult
probe(profile) -> CapabilityReport
```

`ModelResult` includes:

- model call ID;
- logical role and profile version;
- provider/model identifier;
- raw completion retained according to policy;
- parsed output when successful;
- finish/stop reason;
- prompt/completion/total token usage when available;
- latency and retry count;
- provider request ID;
- capability mode used;
- normalized error or fallback record.

The gateway owns:

- provider selection and capability probing;
- OpenRouter and later local OpenAI-compatible adapters;
- timeout and retry mapping;
- structured-output capability selection;
- context/output budget enforcement;
- sampling configuration;
- usage and quota records;
- redaction before external trace export;
- provider error normalization.

Provider SDK types never escape the infrastructure adapter.

## 4. Model profiles

Profiles are immutable versioned configuration records containing:

```text
logical role
provider and model slug
prompt/template versions
structured-output strategy
context and output budgets
sampling parameters
timeout
retry/fallback policy
capability requirements
content/data policy
active date and status
```

Do not hard-code one transient `:free` model slug into domain or graph code. Runtime probes determine availability, JSON-schema support, context limits, and embedding dimensions. Profile changes create a new version and do not rewrite historical call metadata.

## 5. Bounded LangGraph workflows

### CharacterDecisionGraph

```text
START
 -> validate invocation context
 -> render perspective-safe prompt
 -> call character model
 -> validate Intent schema
 -> deterministic permission/knowledge precheck
 -> repair once when structurally malformed
 -> return proposal or deterministic WAIT fallback
 -> END
```

It cannot call repository write tools or author another character's reaction.

### DirectorProposalGraph

```text
START
 -> evaluate deterministic trigger/cooldown
 -> if no trigger: return no-op
 -> assemble bounded omniscient context
 -> call Director model
 -> validate proposal shape, privileges, budgets, and prerequisites
 -> repair once or reject
 -> return proposal/no-op
 -> END
```

### ReactionGraph

Receives one observable attempt and one participant perspective. It returns a bounded reaction intent. It cannot see the initiating actor's hidden rationale unless that rationale is observable.

### ResolutionGraph

```text
START
 -> deterministic feasibility/rule evaluation
 -> if outcome is determined: return deterministic resolution
 -> otherwise create bounded ambiguity packet
 -> call resolver model
 -> validate resolution against feasible envelope
 -> repair once or choose deterministic fallback
 -> return typed resolution proposal
 -> END
```

No remote call occurs in the canonical commit transaction.

### NarrationGraph

Receives committed event/effects and an audience-visible fact set. Returns noncanonical narration beats. If generation fails, presentation falls back to structured event text. Narration cannot add an event, item, injury, relationship, location, or fact absent from its input.

### MemoryConsolidationGraph

Receives one owner's sourced observations and memories. Returns versioned summary, belief-update, relationship-evidence, and long-term-memory proposals. Application validators enforce provenance, owner scope, and allowed claim IDs before commit.

## 6. Graph state contract

Graph state may include:

```text
graph_run_id
task_run_id
world_id
phase_run_id
snapshot_id
scene_id
actor/observer ID
context_manifest_id
model role/profile/prompt versions
proposal and validation errors
repair count
operational status
```

Graph state must not include authoritative mutable projections, unrestricted repositories, provider credentials, or unsourced long-term memory.

Use a task-run UUID as LangGraph `thread_id`. Do not use a permanent character ID as an eternal thread. Character identity is reconstructed from canonical data and context assembly.

## 7. Checkpoints and stores

- Persistent LangGraph checkpointers support bounded graph resume and human interrupts.
- Use PostgreSQL-backed checkpoints in a separate schema or unmistakably prefixed tables.
- A graph checkpoint is operational and may be pruned after retention requirements.
- Deleting a completed graph checkpoint must not lose canon, model-call audit data, or character memory.
- Do not use LangGraph Store as a second domain memory database.
- Application repositories remain the only route to observations, beliefs, memories, and world data.

## 8. Context Assembler

The assembler accepts a typed request:

```text
model role
audience/actor identity
world, phase snapshot, scene, and task IDs
as-of event sequence
allowed data classes
retrieval purpose
section/token budgets
tool policy
```

Pipeline:

1. Authenticate application caller and role.
2. Resolve the immutable phase/snapshot and aggregate versions.
3. Apply owner, visibility, location, participation, and role filters in structured queries.
4. Retrieve deterministic recent data.
5. Retrieve long-term candidates only after mandatory filters.
6. Score candidates using semantic similarity, salience, recency, goal relevance, entity overlap, emotional relevance, and unresolved commitments.
7. Deduplicate and enforce per-section budgets.
8. Delimit lore, memories, dialogue, and user text as untrusted data.
9. Produce an immutable `ContextEnvelope`.
10. Persist a `ContextManifest` before or atomically with model-call registration.

A graph may shorten or reorder already-authorized content within declared budgets. It may not widen source scope.

## 9. Context envelope

Suggested versioned sections:

- role and behavioral instructions;
- response schema and allowed tools;
- stable character identity/card excerpt;
- current perceived surroundings;
- actor's own dynamic state and inventory;
- active goals, plans, commitments, and activities;
- known entities and directional relationships;
- recent observations and memories;
- retrieved long-term memories;
- public and locally known lore;
- current observable scene attempts;
- output budget and fallback instruction.

Every section distinguishes instructions from untrusted data. Recent memory does not grow the stable system prompt.

## 10. Context manifest

Persist:

- manifest ID and schema version;
- call/task/graph/world/phase/snapshot/scene/actor IDs;
- role and perspective policy version;
- source IDs, types, versions, owner, and visibility class;
- retrieval query, mandatory filters, ranking features, and final score;
- inclusion or exclusion reason;
- estimated tokens per section;
- truncation/deduplication decisions;
- prompt template and model profile versions;
- rendered-context hash;
- permitted tools;
- creation time.

The default audit UI may display metadata without exposing hidden raw content to a player-scoped session.

## 11. Model tools

Prefer explicit read-only tools with typed inputs and bounded outputs:

- inspect known entity summary;
- retrieve owner-scoped memories;
- inspect known map route;
- check actor capability/resources;
- inspect active goal/activity;
- resolve public/local lore definition.

Rules:

- no arbitrary SQL, filesystem, shell, HTTP, or repository access;
- no canonical write tool;
- no tool that returns hidden fields and asks the model to ignore them;
- every invocation receives actor/role/task scope from runtime context, not model arguments alone;
- tool results enter the context manifest and trace;
- bounded result counts and byte/token sizes;
- repeated tool calls consume explicit budgets.

## 12. Structured output and repair

For state-affecting roles:

1. Prefer provider-native strict JSON Schema when capability-probed.
2. Retain provider-independent extraction and Pydantic validation.
3. Reject extra fields and unknown effect types.
4. Perform deterministic semantic validation after schema validation.
5. Allow at most one bounded repair/regeneration by default.
6. Use a deterministic fallback, no-op, safe wait, or visible terminal task failure.
7. Never parse arbitrary narrative tags into canonical mutations.

Narration may use structured beats rather than one plain string:

```text
speaker_id or narrator
visible text
beat kind
emotion/expression hint
source event/effect IDs
```

Expression hints affect presentation only.

## 13. Tracing layers

### Durable product trace

PostgreSQL records the authoritative chain:

```text
phase_run
 -> task_run
 -> graph run/checkpoint ID
 -> context_manifest
 -> model_call
 -> proposal
 -> validation/resolution
 -> world_event/effects
 -> observations/memories/outbox
```

This trace is required even when external observability is disabled.

### LangSmith development/evaluation trace

Enable selectively by environment. Add inherited tags and metadata through LangChain `RunnableConfig`:

- environment and application version;
- graph name/version;
- world, phase, scene, task, and actor IDs;
- model role/profile/prompt version;
- context manifest ID;
- retry/repair/fallback status;
- provider request ID;
- committed event ID when available.

Do not attach API keys, connection strings, raw hidden-character context to player-visible projects, or personal data. LangSmith is never canon and disabling it must not affect gameplay.

## 14. Budgets and fallback

Reserve an estimated request budget before starting a phase unit that cannot safely stop halfway. Track by role/profile:

- request count;
- token estimate and actual usage;
- provider quota status;
- repair/fallback count;
- latency;
- cost when applicable.

On unavailable provider or exhausted quota:

- do not begin an unsafe multi-call unit;
- use deterministic WAIT/continue-activity outcomes where valid;
- pause at a safe boundary if a required creative step has no valid fallback;
- never advance to the next phase with unresolved required canonical work.

## 15. Prompt lifecycle

- Store prompts as versioned repository files.
- Separate stable role instructions, response schema, and dynamically assembled context.
- Record prompt version and rendered hash for every call.
- Use fixture-based rendering tests for escaping, section order, token budgets, and forbidden-source exclusion.
- Prompt changes that alter structured semantics require schema/evaluator review.
- Do not test prose wording snapshots unless wording itself is a product contract.

## 16. Evaluation hooks

Every graph exposes fixture-driven execution with fake models. Capture:

- structural validity;
- repair and fallback paths;
- permission and knowledge violations;
- context source precision/recall;
- secret leakage;
- character voice and decision distinctness;
- causal support for proposed effects;
- narration contradiction and unsupported-fact rates;
- latency/token budgets.

Evaluation results inform profile and prompt versions. They do not mutate canon.

## 17. Promotion constraints

Do not promote a model-backed role until:

- its schema and deterministic validators exist;
- fake success, malformed, refusal, timeout, 429, and duplicate-result paths pass;
- context manifests prove owner/visibility scope;
- its deterministic fallback or safe failure is defined;
- remote calls are absent from database transactions;
- trace correlation reaches the source event or terminal rejection;
- disabling LangSmith has no behavioral effect.