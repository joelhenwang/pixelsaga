# Product Charter and Scope

**Status:** Normative product contract
**Primary user:** One local user
**Initial content:** English, young-adult soft-dark anime-inspired fantasy

## 1. Product statement

Build a persistent, self-evolving fantasy world that can be watched autonomously or influenced interactively. The world must behave as a causal simulation rather than a sequence of disconnected model completions.

Characters have durable identities, limited knowledge, goals, plans, relationships, capabilities, memories, and histories. Deterministic systems own time, movement, resources, injury, schedules, and canonical outcomes. Models propose character choices, narrative opportunities, ambiguous resolutions, memories, and presentation. The user interacts through a pixel-art visual-novel timeline.

The long-term maximum scope is one canonical world, one active timeline, and three focus-family generations.

## 2. Product principles

1. **Coherence over spectacle.** A quiet causal event is better than an impressive contradiction.
2. **Agency over forced plot.** Characters can reject quests, relationships, director proposals, and user expectations.
3. **Simulation truth, narrative presentation.** Structured state determines facts; prose frames committed facts.
4. **Perspective is real.** Characters can be wrong, deceived, biased, unaware, or forgetful.
5. **Quiet life matters.** Travel, work, rest, relationships, routine, and uneventful phases are legitimate outcomes.
6. **User power is explicit.** Every intervention uses a named role, permission set, and audited command.
7. **Local-first evolution.** Initial remote models are replaceable by local services without changing canon or identity.
8. **Inspectability.** Every state change, model call, context source, retry, and perception must be traceable.
9. **Visual continuity.** Images support identity and atmosphere but never override structured world truth.
10. **Bounded ambition per stage.** Each stage proves one coherent capability before expanding breadth.

## 3. Target experience

At each detailed phase:

1. The deterministic World Engine advances time-dependent systems.
2. The system seals an immutable phase snapshot.
3. The Narrative Director may propose a justified opportunity, hook, or pacing adjustment.
4. Eligible focus characters independently propose one primary action from their own perspective.
5. The Scene Assembler groups interacting and conflicting intents.
6. Participants may produce bounded reactions to observable attempts.
7. Deterministic rules and bounded model judgment resolve each scene into typed effects.
8. Effects, events, projections, observations, immediate memories, and outbox work commit atomically.
9. Narration presents the committed event to the selected audience perspective.
10. Salient committed events may enqueue pixel-art image work.
11. The user watches the timeline or acts through the current role at safe boundaries.

## 4. User roles

### Watcher

Read-only fictional role. May inspect omniscient world state, timelines, perspectives, model calls, context manifests, and debug traces when debug access is enabled. Operational pause/resume remains a separately granted control.

### Director

May propose themes, hooks, arcs, NPCs, locations, pacing pressure, or future opportunities. Director input follows ordinary validation and cannot force character reactions or scene outcomes.

### Deity

May execute configured authoritative overrides such as altering entities, resources, memories, rules, injuries, or life status. Every override is a typed, audited event. Hard retcons preserve history, taint dependent projections, and trigger a consistency audit.

### Player

Controls one selected persistent character's attempted primary action and optional dialogue. Receives only that character's permitted perspective. Controls attempts, not outcomes. Cannot declare inaccessible knowledge, another actor's reaction, or impossible effects as fact.

## 5. Operating modes

| Mode | Behavior |
| --- | --- |
| Automatic | Advances phases until paused, ended, blocked by a fatal operational error, or stopped at a configured approval boundary |
| Manual phase | User starts each phase; that phase runs to a safe completion boundary |
| Debug step | Pauses at selected state-machine transitions such as snapshot, intent, assembly, pre-commit, or observation |
| Player control | Automatic or manual simulation with one focus character's primary intent supplied by the user |
| Macro simulation | Stage 5 lower-resolution day/week/month/year advancement with high-salience interruption |

## 6. Initial world and time model

- Exactly one world and one active timeline.
- Ten detailed phases: dawn, sunrise, morning, noon, afternoon, sunset, dusk, evening, night, midnight.
- Fictional time does not advance while the service is stopped unless a command explicitly advances it.
- Every phase starts with deterministic world updates.
- Activities may span phases and define progress, resource use, completion, and interruption conditions.
- A phase is complete only when canonical scenes, observations, immediate memories, and required outbox records are committed.
- Images and noncritical memory consolidation never block phase completion.

## 7. Character model

The initial detailed cast grows by stage to two main and two sub-main focus slots.

A persistent character has:

- a versioned identity card: identity, history, appearance, personality, values, fears, desires, voice, boundaries, capabilities, secrets, and initial knowledge;
- dynamic state: location, life status, injuries, conditions, stamina, mana, emotions, needs, goals, plans, activities, relationships, beliefs, and optimistic version;
- perspective-owned observations and memories;
- sourced evolution through events rather than silent profile rewriting.

Foundational history is not a mutable transcript. Death is normally permanent unless explicit world lore provides a rare, costly mechanism.

## 8. Scene and agency rules

- Every eligible focus character receives the same sealed phase snapshot version but a different perspective envelope.
- One primary intent is proposed per eligible focus character per phase.
- Stable action families coexist with free-form intent and desired effects.
- `WAIT`, `REST`, `OBSERVE`, and `CONTINUE_ACTIVITY` are first-class choices.
- A character authors its attempt, not another character's private response.
- Interacting intents share a scene and atomic outcome boundary.
- Dialogue, negotiation, chase, and combat interactions have explicit beat budgets.
- Outcomes support success, partial success, failure, interruption, and invalidation.
- Invalid model output follows one bounded repair/regeneration path, then a deterministic safe fallback or visible task failure.

## 9. Rules identity

The initial rules are **D&D-inspired**, not a 5e implementation:

- common 0-100 base stats;
- separate skills and sourced progress evidence;
- stamina and mana as short-term resources;
- body-region injuries, pain, bleeding, mobility, consciousness, treatment, recovery, and lasting consequences;
- magic definitions with prerequisites, costs, cast time, range, failure modes, and counters;
- seeded uncertainty plus deterministic feasibility and bounded resolver judgment;
- no universal HP pool.

A future 5e-compatible mode requires a separate approved product decision, rules contract, persistence model, content-license review, and stage plan. It must not leak 5e assumptions into the initial world engine.

**Recorded product decision 2026-09-16:** the shipped D&D track (d20
attacks/saves, AC, HP pools for party and monsters, 5e SRD content
tables) is canonical, not a future mode. The no-HP injury model in
section 9 stays a later complement (severity, treatment, recovery),
not a replacement. Charter section 15's HP-replacement gate is
satisfied by this record.

## 10. Knowledge and memory

Objective events, observations, claims, beliefs, rumours, and memories are distinct records.

- Observation eligibility depends on location, participation, senses, communication, and concealment.
- Dialogue creates claims, not objective facts.
- Characters may hold false or uncertain beliefs.
- Recent memory remains relational and directly queryable.
- Long-term memory retains owner, visibility, provenance, confidence, source IDs, and embedding version.
- Visibility and owner filters run before semantic search.
- Retrieved memory, lore, dialogue, and user text are untrusted prompt data.

## 11. Visual-novel product surface

The mature client provides:

- chronological visual-novel scenes;
- reusable character portraits, expressions, outfits, and location backgrounds;
- optional salient event illustrations;
- suggested actions and free-form player intent;
- character cards, state, skills, relationships, goals, plans, injuries, memories, and history;
- canonical and perspective-filtered encyclopedia views;
- known/unknown map views;
- character diaries;
- role, mode, pause, step, retry, and operational controls;
- queue, model, and worker diagnostics in debug views.

PixelSaga informs presentation and interaction patterns but not internal state ownership or compatibility requirements.

## 12. Narrative quality

The default tone supports adventure, romance, humour, growth, mystery, politics, slice of life, danger, grief, betrayal, and non-graphic horror.

The product must resist:

- constant emotional self-explanation;
- repetitive dramatic one-liners;
- automatic friendship-to-romance conversion;
- consequence-free failure;
- generic cruel villains;
- side characters who exist only to praise protagonists;
- repeated locations, phrases, emotional shapes, and participant combinations;
- lore-dump dialogue;
- disruptive Director events every phase.

Quality is measured through scenarios, trace analysis, deterministic repetition metrics, model-based evaluators, and human review. It is not inferred from model size.

## 13. Stage product proofs

| Stage | Product proof |
| --- | --- |
| 0 | One seeded deterministic phase survives crash/retry without duplicate canon |
| 1 | Two characters complete three phases from one snapshot with perspective differences, one interaction scene, narration, and restart safety |
| 2 | Four focus characters complete seven detailed days with activities, Director restraint, relationships, claims, and a usable visual-novel client |
| 3 | Thirty autonomous days complete with bounded quality, long-term retrieval, fantasy conflict rules, and asynchronous remote image generation |
| 4 | The same world runs against replaceable local text/embedding workers and local ComfyUI without identity or canon changes |
| 5 | Macro simulation reaches a generation transition while preserving genealogy, public history, causality, and high-salience interruption |

## 14. Explicit exclusions

Not initial requirements:

- PixelSaga save, API, plugin, or UI parity;
- multiplayer or public SaaS tenancy;
- public content sharing and moderation;
- multiple worlds or normal branching timelines;
- wall-clock simulation while services are stopped;
- autonomous simulation of every citizen;
- physics-engine fidelity;
- deterministic reproduction of stochastic remote model text;
- actual D&D 5e compatibility;
- character-specific model fine-tuning;
- explicit adult content;
- automatic canonicalization of image details;
- Temporal, Redis, microservices, or Kubernetes before measured need.

## 15. Change control

The following require an explicit product decision before implementation:

- replacing the no-HP ruleset with 5e mechanics;
- supporting multiple canonical worlds or branches;
- adding public sharing or multi-user access;
- making generated prose or images canonical;
- changing the four focus-slot model;
- changing the ten-phase calendar;
- allowing Director proposals to bypass ordinary outcome validation;
- changing content boundaries;
- enabling offline wall-clock advancement.
