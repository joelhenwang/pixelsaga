# Stages 2 to 5 Execution Plan

**Status:** Executable stage task catalogue

# Stage 2: Seven-Day Playable World

**Stage ID:** `stage2-seven-day-v1`
**Outcome:** Four focus characters complete seven detailed days across all ten phases with activities, restrained Director behavior, relationships, claims/beliefs, role switching, and a usable visual-novel client.

## Stage 2 dependency order

```text
S2-CONTRACT-001
 -> S2-TIME-001 + S2-CAST-001 + S2-ACTIVITY-001
 -> S2-REL-001 + S2-KNOW-001 + S2-PROGRESS-001
 -> S2-DIRECTOR-001 + S2-SUMMARY-001
 -> S2-ORCH-001 + S2-ROLE-001
 -> S2-API-001
 -> S2-UI-MOCK-001 -> product-owner selection -> S2-UI-001
 -> S2-GATE-001
```

## Stage 2 task packets

### S2-CONTRACT-001: Stage 2 contracts and migration

Add versioned activity, route, inventory/item, skill/progress, directional relationship, claim, belief, narrative hook/arc, focus-slot, user-role, and override contracts. Add only database tables and columns exercised by the seven-day scenario.

**Acceptance:** strict schemas, migration from promoted Stage 1 fixture, prior data preserved, generated contracts updated.

### S2-TIME-001: complete detailed calendar and schedules

Implement all ten phases, day rollover, scheduled effects, phase eligibility, quiet-phase detection, and world-first deterministic tick behavior.

**Acceptance:** full-day transition property tests; restart at every phase boundary; no phase starts over incomplete prior work.

### S2-CAST-001: four focus slots and character evolution

Add two main and two sub-main focus assignments, card-version changes through sourced events, goals, plans, needs, and lower-resolution NPC lifecycle classes.

**Acceptance:** four characters generate distinct perspective contexts; ordinary NPCs never auto-promote; card history remains immutable.

### S2-ACTIVITY-001: travel and persistent activities

Implement activity start/progress/complete/interrupt for travel, rest, training, work, and one content-specific activity. Add routes, durations, resource costs, and interruption conditions.

**Acceptance:** activities continue through quiet phases without unnecessary model calls; interruption and restart are idempotent; travel cannot place an entity in two locations.

### S2-REL-001: directional relationships

Implement sourced relationship evidence and independent source-to-target dimensions. Context and UI expose only permitted own/inferred relationship information.

**Acceptance:** A-to-B and B-to-A differ; a scene updates only validated directions; no narration-only relationship mutation.

### S2-KNOW-001: claims and beliefs

Implement communicated claims, listener eligibility, belief confidence/provenance updates, contradiction support, and bounded forgetting behavior without deleting sources.

**Acceptance:** a false claim does not change objective canon; different listeners form different beliefs; private claims do not leak through retrieval/read models.

### S2-PROGRESS-001: inventory, resources, skills, and evidence

Implement item instances/ownership, stamina/mana bounds required by enabled content, skill definitions, training evidence, repetition limits, and deterministic progress calculation.

**Acceptance:** one item has one owner; duplicate training action does not double progress; model prose cannot award progression.

### S2-DIRECTOR-001: triggered DirectorProposalGraph

Implement deterministic trigger/cooldown checks, bounded omniscient context, Director profile/prompt, hook/arc proposals, privileges, NPC/location budgets, one repair, and no-op fallback.

**Acceptance:** Director does not run every phase; rejected opportunities do not force outcomes; unsupported permanent change is rejected; model outage leaves safe world progression.

### S2-SUMMARY-001: perspective daily summaries

Implement post-day summary proposals from one owner's observations/recent memories, provenance manifest, contradiction/visibility validation, and versioned non-authoritative summary records. No vector retrieval affects decisions yet.

**Acceptance:** summaries differ by perspective, retain source IDs, do not replace raw records, and survive regeneration/versioning.

### S2-ROLE-001: Watcher, Director, Deity, and Player commands

Implement role selection at safe boundaries, role permissions, Director user proposals, player-controlled intent substitution, and typed Deity overrides/hard-retcon markers.

**Acceptance:** server enforces permissions; every intervention is audited; player receives limited context; Deity changes create events and consistency consequences.

### S2-ORCH-001: seven-day orchestrator

Extend orchestration across ten phases, four concurrent primary intent tasks, quiet-phase suppression, activities, Director triggers, daily summaries, pause/resume, quota reservation, and recovery.

**Acceptance:** seven-day fake scenario completes after injected failures with no missing/duplicate scenes or partially canonical phases.

### S2-API-001: Stage 2 read and command surface

Add timeline, map, diary, relationship, goal/activity, role, mode, Director, Deity, and operations endpoints plus event notifications and generated client updates.

**Acceptance:** each role sees only permitted projections; stale commands conflict cleanly; cursor replay rebuilds client state.

### S2-UI-MOCK-001: full application direction mocks

Create distinct static HTML/JavaScript mocks for timeline/visual novel, character detail, map, diary, and operations views in desktop/mobile and dark/white modes. Use realistic seven-day data. Stop for product-owner selection before production component changes.

### S2-UI-001: usable Vue product surface

Implement the selected visual direction, routes, role switcher, automatic/manual controls, player action, timeline, visual-novel scene, character pages, map, diary, relationships, goals/activities, and operations queue. Use deterministic/manual visual assets.

**Acceptance:** actual browser verification across desktop/mobile/keyboard/reduced-motion, reconnection, delayed narration, phase advancement, player action, and role filtering.

### S2-GATE-001: seven-day promotion

Run seven days with deterministic fakes and a bounded opt-in live-provider sample. Produce consistency, perspective, quality, call-budget, performance, recovery, accessibility, migration, and security evidence.

## Stage 2 hard gate

- all ten phases and day rollover behave deterministically;
- four focus characters use same-phase snapshots and distinct perspectives;
- travel/activities persist, interrupt, and recover;
- Director trigger rate remains within fixture limits and no-op is normal;
- claims never become objective facts without causal events;
- directional relationships evolve from evidence;
- duplicate work creates no duplicate inventory/progress/canon;
- user roles are server-enforced and audited;
- daily summaries preserve perspective/provenance;
- injected model/process failures leave no incomplete phase after reconciliation;
- visual-novel client is usable and contains no world rules;
- zero hard invariants or seeded-secret leaks.

# Stage 3: Thirty-Day Memory, Rules, Images, and Quality

**Stage ID:** `stage3-thirty-day-v1`
**Outcome:** Thirty autonomous days complete with perspective-safe long-term retrieval, bounded fantasy conflict/magic, asynchronous pixel-art generation, and measurable narrative quality.

## Stage 3 dependency order

```text
S3-MEM-001 -> S3-EMBED-001 -> S3-RETRIEVE-001 -> S3-MEMEVAL-001
S3-RULE-001 -> S3-INJURY-001 -> S3-COMBAT-001 + S3-MAGIC-001
S3-VISUAL-001 -> S3-IMAGE-001
S3-QUALITY-001
all -> S3-ORCH-001 -> S3-UI-001 -> S3-GATE-001
```

## Stage 3 task packets

### S3-MEM-001: long-term memory lifecycle

Implement salience calculation, recent-to-long-term promotion, daily and monthly compaction, source retention, belief/relationship proposal validation, unresolved commitment tracking, and forgetting as reduced retrieval probability.

**Acceptance:** source records remain available; summaries cannot introduce inaccessible facts; retries do not duplicate memory.

### S3-EMBED-001: versioned embedding pipeline

Implement outbox-driven embedding tasks, model/prefix/content versions, exact-dimension validation, idempotent rows, re-embedding into parallel active versions, outage backlog, and no effect on immediate recent memory.

**Acceptance:** failure does not block simulation; owner/visibility metadata is mandatory; dimension/version mismatches fail safely.

### S3-RETRIEVE-001: hybrid perspective-safe retrieval

Apply world/owner/visibility/time filters before exact vector search, then score similarity, salience, goal relevance, recency, entity overlap, emotional relevance, and unresolved commitments. Deduplicate and fit context budgets.

**Acceptance:** seeded important memories rank appropriately, hidden memory cannot become a candidate, and every returned record appears in the context manifest.

### S3-MEMEVAL-001: retrieval evaluation

Build deterministic query/expected-source scenarios for promises, discoveries, relationships, false beliefs, secrets, old salient events, and distractors. Record recall, precision, leakage, latency, and token cost by retrieval version.

**Acceptance:** promotion targets in [11_TESTING_AND_EVALUATION.md](11_TESTING_AND_EVALUATION.md) pass; no approximate index is added without latency evidence.

### S3-RULE-001: mature action and effect families

Enable communicate, interact, use/transfer item, train, work, craft, help, hide, search, attack, defend, and cast-magic families with permissions, capability checks, effect schemas, and deterministic fallbacks.

**Acceptance:** every enabled action has validation, effect, retry, observation, and UI behavior; unsupported desired effects cannot pass as prose.

### S3-INJURY-001: health, condition, and recovery

Scope note (decision 2026-09-16): HP pools are canonical from the
Stage 1/2 D&D track. This packet adds severity, treatment, recovery,
and lasting consequences on top; it does not remove HP.

Implement body-region injuries, severity, pain, bleeding, mobility/consciousness consequences, treatment, recovery, complications, and permanent outcomes.

**Acceptance:** no HP; injuries have source events; recovery follows time/rules; duplicate treatment has one result.

### S3-COMBAT-001: combat vertical slice

Implement attempt/reaction/defense, positioning/equipment/skill conditions, seeded uncertainty, retreat/surrender/interruption, injury effects, beat budgets, and atomic scene resolution.

**Acceptance:** success/partial/failure/death paths; weaker victory requires causal support; narration cannot alter resolution; restart/duplicate safety.

### S3-MAGIC-001: magic vertical slice

Implement spell definitions/knowledge, prerequisites, mana/material costs, cast time/range/area, concentration/activity behavior, counters, failure, and observable signatures.

**Acceptance:** unknown or unaffordable casts fail; creative uses remain within effect envelope; resources commit atomically with results.

### S3-VISUAL-001: versioned visual state

Implement character/location visual versions, appearance source events, reusable asset references, historical version retention, visual style packs, and audience-visible image specification inputs.

**Acceptance:** current appearance changes do not rewrite historical scenes; image prompts use only allowed committed facts.

### S3-IMAGE-001: remote image gateway and worker

Implement provider-neutral image protocol, fake adapter, one selected remote adapter, outbox jobs, idempotency, retry/backoff, asset metadata/storage abstraction, optional quality checks, manual regeneration, and UI notifications.

**Acceptance:** image outage/backlog does not block phases; duplicate job creates one logical output; hallucinated visual details never update canon.

### S3-QUALITY-001: narrative quality system

Implement deterministic repetition/trope/participant/location/Director-frequency metrics, evaluator rubrics, trace-to-dataset export, human review workflow, and version comparison reports.

**Acceptance:** metrics detect seeded repetition and forced-romance fixtures without rejecting valid quiet scenes; evaluator results never write canon.

### S3-ORCH-001: month-capable orchestration

Integrate memory jobs, richer rules, combat/magic, image jobs, quality telemetry, budgets, and pause/degradation policies. Separate worker process only if required for measured responsiveness or isolation.

**Acceptance:** 30-day soak resumes from injected failure points, stays within call/task budgets, and completes required canon despite image/embedding outages.

### S3-UI-001: mature local product views

After static-mock selection for new surfaces, implement encyclopedia, gallery, richer known/unknown map, memory provenance/debug view, injuries/conditions/magic, visual asset states, and evaluation/operations summaries.

**Acceptance:** role filtering, historical image placement, delayed assets, trace navigation, and accessibility verified in the actual browser.

### S3-GATE-001: thirty-day promotion

Produce deterministic and bounded live-model soak evidence, retrieval dataset results, narrative evaluator report, image backlog test, combat/magic scenario, full consistency audit, and resource/cost profile.

## Stage 3 hard gate

- 30 days complete with zero hard invariants;
- zero seeded secret leakage;
- zero duplicate canonical effects;
- all projection changes retain source event/version;
- at least 95% structurally valid state-affecting responses after one repair;
- at least 90% recall of seeded important promises/discoveries;
- bounded unsupported-memory/narration claims under approved evaluator threshold;
- distinct voices/decision patterns meet rubric;
- NPC, trope, Director, and model-call growth stay within configured budgets;
- combat and magic respect deterministic feasibility and typed effects;
- image and embedding outages do not block textual canon;
- exact vector search latency is measured before index promotion.

# Stage 4: Local Models and Image Workers

**Stage ID:** `stage4-local-topology-v1`
**Outcome:** The Stage 3 world runs through replaceable local text/embedding services and local ComfyUI while preserving identity, contracts, traces, and canon.

## Stage 4 task packets

### S4-BENCH-001: model and hardware benchmark

Benchmark candidate local text and embedding models against frozen Stage 3 datasets: schema adherence, decision quality, perspective leakage, resolution support, narration, memory, latency, throughput, VRAM/RAM, and failure behavior.

**Acceptance:** evidence-backed selected profiles; no model is selected by size or anecdote alone.

### S4-TEXT-001: local text adapter and routing

Implement OpenAI-compatible local adapter, capability probes, health, bounded concurrency, profile routing, timeout/failover, and two worker targets when hardware supports them.

**Acceptance:** character identity/output contract is unchanged when routed between compatible workers; worker death retries safely.

### S4-EMBED-001: local embedding migration

Implement local adapter, new embedding version, parallel re-embedding, evaluation comparison, active-version cutover, and rollback.

**Acceptance:** no mixed dimensions; retrieval filters remain unchanged; old version remains available until new evaluation passes.

### S4-COMFY-001: ComfyUI workflow

Create versioned pixel-art portrait/background/event workflows, parameter schema, health/capability probe, queued execution, output validation, and reproducible workflow metadata.

**Acceptance:** workflow failure is retryable; asset records include model/workflow/style/source versions; no canon changes.

### S4-ASSET-001: object storage promotion

Introduce an S3-compatible adapter only if Stage 3 asset evidence justifies it. Implement content-addressed keys/checksums, metadata transaction, garbage-collection safety, backup, and restore.

**Acceptance:** DB never references missing promoted assets; orphan cleanup cannot delete live historical assets.

### S4-ROUTE-001: resource-aware routing and backpressure

Implement role-specific concurrency limits, queue priority, budget reservation, health-based routing, load shedding, and visible operational status.

**Acceptance:** overload pauses/degrades at safe boundaries; high-priority phase work is not starved by images/evaluations.

### S4-TEMPORAL-001: promotion assessment

Measure database orchestrator reliability and complexity against explicit criteria. If it passes, document deferral. If it fails and Temporal is approved, implement an adapter around existing application tasks; never place business rules or canon in workflow history.

**Acceptance:** evidence and decision record. Temporal is not required merely because Stage 4 exists.

### S4-GATE-001: topology promotion

Run frozen Stage 3 evaluation subset and fault scenarios across remote and local profiles. Kill text, embedding, and image workers during jobs. Verify failover/backlog/restart, identity portability, context trace integrity, and unchanged canonical transaction behavior.

## Stage 4 hard gate

- one application contract serves remote and local adapters;
- worker routing does not alter character identity data;
- lost worker work is retried without duplicate canon;
- local embedding version passes retrieval evaluation before activation;
- ComfyUI backlog/outage does not block phases;
- resource contention cannot corrupt or partially commit a phase;
- every local call remains correlated and inspectable;
- topology can return to the prior promoted remote profile.

# Stage 5: Macro Simulation and Generations

**Stage ID:** `stage5-generations-v1`
**Outcome:** Quiet time advances at adaptive resolution and reaches a generation transition with preserved causality, genealogy, public history, and high-salience detailed scenes.

## Stage 5 task packets

### S5-CONTRACT-001: macro and genealogy contracts

Add macro period run, aggregate effect, interruption, genealogy, lineage character, focus assignment, era summary, and end-condition evidence schemas.

**Acceptance:** strict versions/migrations; no automatic private-memory inheritance.

### S5-MACRO-001: deterministic macro engine

Implement day/week/month/year advancement for schedules, activities, ageing, recovery, resources, faction/economy aggregates, relationships, births/deaths, and delayed effects.

**Acceptance:** macro result decomposes into sourced typed effects/events; repeated run is idempotent; no silent state jump.

### S5-SALIENCE-001: resolution selection and interruption

Implement deterministic eligibility for macro resolution, configured quietness thresholds, high-salience candidate detection, and return to detailed phase simulation.

**Acceptance:** seeded major event interrupts macro progression at the correct fictional time; quiet intervals avoid detailed model calls.

### S5-GENEALOGY-001: family and lineage

Implement parent/child relationships, lineage identity, age/life status, public history, and succession eligibility. Do not simulate all descendants as focus characters.

**Acceptance:** family links and dates are consistent; private memories are not inherited without explicit lore mechanism.

### S5-FOCUS-001: focus-slot succession

Implement event-driven assignment from current focus slots to eligible lineage characters at safe boundaries, including card/state/context version transitions.

**Acceptance:** ordinary NPCs do not auto-promote; history remains attached to entity IDs; old focus characters remain queryable.

### S5-SUMMARY-001: era and autobiographical summaries

Generate provenance-linked summaries from macro events and perspective-owned sources. Preserve raw events and public/private separation.

**Acceptance:** summary regeneration is versioned; it cannot add unsupported canon; context budgets remain bounded across years.

### S5-END-001: end conditions

Implement sustained world-peace evidence, civilization-eradication evidence, and configured maximum-day evaluation. Store the evidence and final event.

**Acceptance:** one calm scene cannot satisfy peace; ending checks are deterministic and auditable.

### S5-UI-001: macro/generation presentation

After mock selection, add era timeline, genealogy, focus succession, resolution-level controls, macro interruption, and ending evidence views.

**Acceptance:** user can inspect how compressed periods changed state and drill from summaries to source events.

### S5-GATE-001: generation scenario

Run a compressed multi-year deterministic/model-fixture scenario through one succession. Inject restart during macro periods and generation transition. Audit genealogy, memories, events, focus slots, and end conditions.

## Stage 5 hard gate

- macro simulation avoids detailed work for quiet periods;
- every state change still has event/effect provenance;
- high-salience events restore detailed simulation;
- restart and duplicate delivery remain safe;
- genealogy and fictional dates remain consistent;
- focus succession is explicit and versioned;
- private memories do not transfer without lore;
- era summaries are derived and rebuildable;
- ending decisions retain deterministic evidence;
- the world remains inspectable across resolution levels.

# Cross-stage execution rule

No task may import a later-stage abstraction merely to prepare for hypothetical use. A later-stage task may extend an earlier stable port or schema through a versioned change, but it must preserve the earlier stage's promoted evidence fixtures and invariants.