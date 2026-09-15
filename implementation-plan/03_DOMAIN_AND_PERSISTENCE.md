# Domain and Persistence Contracts

**Status:** Normative domain and data design

## 1. Ubiquitous language

| Term | Meaning |
| --- | --- |
| World | The single canonical setting, rules, entities, map, history, clock, and configuration |
| Canon | Committed world events plus validated current projections |
| Phase | One of ten detailed fictional day intervals |
| Phase run | Durable operational execution record for advancing one phase |
| Phase snapshot | Immutable projection used for all same-phase primary intents |
| Intent | One actor's proposed meaningful action from a snapshot |
| Attempt | Validated observable execution of an intent before outcome |
| Reaction | Bounded response by an eligible participant to an attempt |
| Scene | Causally interacting intents, attempts, reactions, and one atomic outcome boundary |
| Desired effect | Non-authoritative description of what an actor hopes to achieve |
| Effect command | Typed candidate mutation; not authoritative until accepted and committed |
| World event | Immutable record of a committed occurrence |
| Projection | Current-state row updated from accepted effects for efficient reads |
| Observation | Perspective-owned record of what an observer could perceive |
| Claim | Proposition communicated by an entity; may be false or uncertain |
| Belief | Confidence-weighted proposition held by one character |
| Memory | Perspective-owned retained representation with provenance |
| Context manifest | Reproducible record of the sources and budgets used for one model input |
| Model profile | Versioned mapping from logical role to provider/model/prompt/sampling/capabilities |
| Task run | Durable retryable operational unit |
| Outbox message | Transactionally recorded post-commit work request |

Code and documentation must not call graph checkpoints, transcript messages, summaries, images, or model outputs canonical.

## 2. Identifier and version rules

- Use UUID-compatible opaque IDs at external and persistence boundaries.
- IDs are immutable and never encode mutable domain data.
- Every mutable aggregate has a monotonic optimistic version.
- Every world event has a monotonically increasing sequence within the world.
- Every schema-bearing record includes a stable type and integer schema version.
- Prompt, model profile, seed, context manifest, visual state, API, and export formats have explicit versions.
- Timestamps distinguish operational UTC time from fictional absolute phase time.
- Random decisions record a deterministic seed, algorithm/version, and result.

## 3. Core aggregates

### World

Owns configuration, lifecycle status, active timeline, absolute phase index, calendar position, deterministic environment references, end conditions, and current phase leadership/version.

### Character

Owns active card version, life status, location, injuries, conditions, stamina, mana, needs, goals, plans, activities, inventory references, skills, relationships from this character, and optimistic version.

A character card version owns stable identity and behavioral specification. Character state owns current mutable state. Memory is stored separately and referenced by owner.

### Location and route

Own spatial identity, hierarchy/region, capacity or access constraints, routes, travel duration/cost modifiers, and discovered/public visibility metadata.

### Scene

Owns source phase snapshot, participants, intents, attempts, reactions, mutable aggregate set, resolution status, committed event, and beat budget. Scene operational state may exist before canon; only its committed event/effects establish world facts.

### Activity

Owns actor, action family, start phase, planned duration, progress, resource requirements, interruption conditions, completion effects, and state.

### Narrative arc/hook

Owns purpose, prerequisites, status, pacing state, eligible participants, allowed effect categories, cooldowns, and source Director/user proposal. An arc creates opportunities; it does not own outcomes.

## 4. Commands

Initial command families:

- `SeedWorld`
- `AdvancePhase`
- `PauseSimulation`
- `ResumeSimulation`
- `SubmitPlayerIntent`
- `SubmitDirectorProposal`
- `ApplyDeityOverride`
- `RetryTask`
- `SkipTask`
- `CreateExport`
- `ImportWorld`

Every state-changing command contains:

```text
command_id
idempotency_key
actor/user role
world_id
expected_versions
command_type and schema_version
payload
audit metadata
```

The API may carry the idempotency key in a header, but the normalized application command stores it explicitly.

## 5. Action families

Start broad and stable:

```text
WAIT
REST
OBSERVE
MOVE
CONTINUE_ACTIVITY
COMMUNICATE
INTERACT
USE_ITEM
TRANSFER
TRAIN
WORK
CRAFT
ATTACK
DEFEND
CAST_MAGIC
HELP
HIDE
SEARCH
OTHER
```

Stage 0 implements only `WAIT`, `REST`, `OBSERVE`, simple `MOVE`, resource change, and recent-memory creation. Later stages activate families only when validation and effect semantics exist.

## 6. Effect commands

Effects are discriminated, versioned structures. Initial and planned categories include:

- advance clock;
- move entity;
- start/progress/interrupt/complete activity;
- adjust stamina or mana;
- transfer or consume item;
- create/update injury or condition;
- change skill progress;
- create claim;
- update belief from sourced evidence;
- update directional relationship evidence/dimensions;
- create entity or location through permitted authority;
- schedule delayed effect;
- start/advance/close arc or hook;
- assign focus slot;
- update life status;
- record observation and immediate memory;
- explicit deity override or hard-retcon marker.

Each accepted effect records source event, ordinal, type/version, affected aggregate IDs, expected prior versions, normalized payload, and deterministic evidence where applicable.

Do not create a generic `set_field` effect for normal gameplay. Deity operations may use broader typed override effects with explicit audit semantics.

## 7. Event contract

A world event records:

```text
world_id
sequence
event_id
event_type and schema_version
fictional_time / absolute_phase_index
phase_run_id and optional scene_id
source command/task/model proposal IDs
participant/entity IDs
summary fields for deterministic queries
visibility classification
random seed/result references
created_at UTC
```

Narration is linked presentation data, not the event body required to reconstruct state.

## 8. State machines

### Phase run

```text
CREATED
-> WORLD_TICKED
-> SNAPSHOT_SEALED
-> DIRECTOR_COMPLETE
-> INTENTS_COMPLETE
-> SCENES_ASSEMBLED
-> SCENES_COMMITTED
-> PERCEPTION_COMPLETE
-> POST_COMMIT_QUEUED
-> COMPLETED
```

`PAUSED`, `RETRYABLE_FAILED`, `TERMINAL_FAILED`, and `CANCELLED` transitions are allowed only at documented boundaries. A completed phase never returns to an earlier state.

### Task run

```text
PENDING -> CLAIMED -> RUNNING -> SUCCEEDED
                    -> RETRY_WAIT -> PENDING
                    -> DEAD_LETTER
                    -> CANCELLED
```

A lease contains owner, claim time, expiry, heartbeat, attempt, maximum attempts, task kind, input version, and idempotency key. Expired work may be reclaimed. A late prior owner cannot overwrite terminal state.

### Scene lifecycle

```text
PROPOSED -> VALIDATING -> READY -> RESOLVING -> RESOLVED -> COMMITTED
                    \-> INVALID
                              \-> RETRYABLE_FAILED / TERMINAL_FAILED
```

### Activity lifecycle

```text
PLANNED -> ACTIVE -> COMPLETED
                  -> INTERRUPTED
                  -> CANCELLED
```

### Image job

```text
PENDING -> CLAIMED -> GENERATING -> QUALITY_CHECK -> READY
                               \-> RETRY_WAIT -> PENDING
                               \-> FAILED
```

Image state never changes canonical scene state.

## 9. Persistence strategy

Use hybrid event history plus transactional projections:

- append immutable world event and effect rows;
- update normalized current-state projections in the same transaction;
- never require normal reads to replay all events;
- retain source event/version links on projection-changing rows;
- provide rebuild and consistency-audit tooling for reconstructable projections;
- take operational snapshots for recovery/export, not fictional branches.

## 10. Schema by stage

### Stage 0 core

Every table must participate in the Stage 0 scenario:

- `world`
- `world_config`
- `world_clock`
- `entity`
- `location`
- `character`
- `character_card_version`
- `character_state`
- `phase_run`
- `phase_snapshot`
- `phase_snapshot_character`
- `world_event`
- `event_effect`
- `observation`
- `recent_memory`
- `aggregate_version`
- `user_command`
- `task_run`
- `outbox_message`
- `model_profile`
- `model_call`
- `context_manifest`

If the Stage 0 scenario cannot meaningfully read or write a listed table, remove it from Stage 0 and schedule it later.

### Stage 1 additions

- `character_intent`
- `scene`
- `scene_participant`
- `attempt`
- `reaction`
- `resolution`
- `narration`
- graph checkpoint tables managed in a separate schema or clearly prefixed namespace

### Stage 2 additions

- `activity`
- `route`
- `inventory_item`
- `item_instance`
- `skill_definition`
- `character_skill`
- `relationship`
- `claim`
- `belief`
- `narrative_hook`
- `narrative_arc`

### Stage 3 additions

- `long_term_memory`
- `memory_embedding`
- `retrieval_evaluation`
- `injury`
- `condition`
- `spell_definition`
- `character_spell`
- `visual_state_version`
- `image_job`
- `visual_asset`

### Stages 4-5 additions

- worker/endpoint capability records as needed;
- object-store references;
- macro period runs and summaries;
- family/genealogy projections;
- focus-slot assignment history;
- end-condition evidence.

Avoid speculative columns and EAV tables. Add schema through reviewed Alembic migrations when a stage writes and queries the data.

## 11. Atomic scene commit algorithm

Inputs:

- idempotency key;
- source command/task IDs;
- world/phase/scene IDs;
- expected versions for every mutable aggregate;
- validated resolution;
- ordered typed effects;
- deterministic observation fact sets;
- required outbox messages.

Algorithm:

1. Perform remote/model work before opening the transaction.
2. Begin transaction.
3. Look up the idempotency record under a uniqueness constraint.
4. If completed with identical input hash, return its existing result.
5. If the key exists with another input hash, return an idempotency conflict.
6. Lock or compare every affected aggregate version in deterministic ID order.
7. Reject stale resolutions before inserting an event.
8. Allocate the next world event sequence.
9. Insert the world event and ordered event effects.
10. Apply effect projectors to normalized current-state rows.
11. Increment affected aggregate versions.
12. Insert observations and immediate recent memories required by the event contract.
13. Insert outbox messages under deterministic idempotency keys.
14. Store result IDs and output hash on the idempotency record.
15. Commit once.
16. Return canonical IDs and new versions.

A crash before commit leaves no canonical event. A crash after commit but before acknowledgement returns the existing result on retry.

## 12. Phase snapshots

A snapshot is immutable after sealing and records:

- world and phase IDs;
- absolute phase index;
- schema/version;
- relevant world/environment versions;
- eligible focus character IDs and versions;
- location/activity/relationship source versions needed by intent generation;
- deterministic content hash;
- seal timestamp and source phase-run state.

Character context may project less data than the snapshot contains, but all same-phase primary intents reference the same snapshot.

## 13. Observation, claim, belief, and memory boundaries

- An event is objective canon.
- An observation contains only permitted event facts for one observer.
- A claim records what a speaker communicated, not whether it is true.
- A belief records one character's confidence and provenance.
- A memory retains an observation, interpretation, belief, or reflection with owner and source links.
- A summary compresses sources but never deletes or replaces their authority.
- Forgetting reduces retrieval probability or confidence; it does not normally delete source records.

## 14. Retcons and corrections

Operational correction repairs corrupt data through an audited migration and does not create fictional canon.

A deity change creates a typed override event. A hard retcon:

1. records the intended replacement and reason;
2. preserves prior event history;
3. marks downstream projections and memories potentially tainted;
4. pauses normal advancement when required;
5. runs consistency and perspective audits;
6. rebuilds reconstructable projections;
7. resumes only after explicit acknowledgement of unresolved inconsistencies.

Normal recovery snapshots never create alternate timelines.

## 15. Seed and content import

- Seed sources use versioned schemas and deterministic IDs.
- Imports validate references, uniqueness, visibility, content boundaries, and value ranges before writing.
- One transaction imports the seed and records `WORLD_SEEDED`.
- Re-importing the same seed version is idempotent.
- Changed seed content requires a new version and explicit migration behavior.
- Prompt/lore strings are untrusted data even when repository-owned.

## 16. Export and restore

A world export includes:

- export/schema version;
- compatible application version range;
- world configuration and clock;
- canonical event/effect history;
- current projections or a verified snapshot;
- observations, memories, task terminal state, prompt/model metadata, and asset references according to export profile;
- content/seed versions;
- checksums and row counts.

Restore validates into a temporary database/schema, verifies constraints and consistency, then promotes atomically. Never partially merge a full-world restore into active canon.

## 17. Hard invariants

- one active world and timeline;
- one phase leader;
- monotonically increasing event sequence and aggregate versions;
- one logical result per idempotency key/input;
- one primary intent per eligible focus character per phase snapshot;
- no event effect without a source event;
- no projection change without a source event or explicit migration;
- no observation containing facts outside its allowed fact set;
- no memory retrieval crossing owner/visibility scope;
- no negative stamina/mana unless the relevant rule explicitly permits bounded debt;
- no entity in two current locations;
- no item instance owned by two inventories;
- no completed phase with unresolved required scenes;
- no narration/image required for canonical phase completion;
- no model call inside an active canonical transaction.