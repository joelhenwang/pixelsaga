# Content, RPG Rules, Narrative, and Image Plan

**Status:** Product-system plan

## 1. Content ownership

Repository content provides versioned definitions and seeds. Runtime state records which versions created or constrained an event. Content is data, not executable model instructions.

```text
content/
  seeds/<world>-<version>/
  definitions/
    species/
    stats/
    skills/
    items/
    conditions/
    injuries/
    spells/
    locations/
    routes/
    activities/
  prompts/
  visual-styles/
  evaluations/
```

Every content bundle includes schema version, content version, stable IDs, provenance, license/attribution metadata, and validation rules.

## 2. Initial seed

Stage 0 uses one deliberately small seed:

- one world and calendar configuration;
- two locations with one traversable route;
- two persistent characters with distinct private facts;
- minimal public lore;
- initial clock and resources;
- only definitions required by `WAIT`, `REST`, `OBSERVE`, and simple `MOVE`.

Stage 1 adds context required for three phases and one interaction scene. Later stages extend the same seed rather than importing a broad untested compendium.

The seed must contain a known secret-isolation fixture: character A knows one proposition that character B does not. Every perspective and retrieval gate uses it.

## 3. Stats and progression

- Base stats use a common 0-100 scale.
- Skills are separate from base stats.
- Potential and growth rate constrain long-term development.
- Species, age, training, personality, injuries, magic, and events may affect development.
- Progress requires sourced evidence from committed actions.
- Difficulty, repetition, training quality, recovery, and potential affect gains.
- A model may propose narrative recognition of improvement; deterministic rules calculate permitted progress.
- Progress and level-like milestones reference source events.

Do not add a universal level or experience system unless a later rules decision requires it.

## 4. Resources, health, and injury

Initial short-term resources:

- stamina;
- mana when magic is enabled;
- bounded needs such as hunger or fatigue only when their stage can produce meaningful decisions.

Health uses:

- body region;
- injury type and severity;
- pain;
- bleeding;
- mobility and consciousness effects;
- treatment state;
- recovery trajectory;
- complications and permanent consequences.

No universal HP pool. Death and unconsciousness follow explicit injury/life-status rules.

Do not build medical simulation detail before one combat/injury vertical slice needs it.

## 5. Action resolution

Resolution order:

1. Validate actor, permission, perspective, target, location, capability, resources, activity conflicts, and expected versions.
2. Determine whether the intent is impossible, automatically successful, or ambiguous.
3. Construct a feasible outcome envelope.
4. Generate bounded reactions from eligible participants when needed.
5. Apply seeded deterministic uncertainty and capability comparison.
6. Use the resolver model only for ambiguity remaining inside the feasible envelope.
7. Produce typed effects and delayed effects.
8. Validate every effect again against current state before commit.

A weaker actor may prevail through preparation, surprise, terrain, teamwork, specific counters, or plausible bounded luck. The resolver may not create an unsupported power-up.

## 6. Combat

Combat is scene-centric rather than turn-parser-driven.

Minimum combat slice:

- declared attempt and target;
- observable reaction opportunity;
- capability, positioning, equipment, condition, and environment checks;
- deterministic seed/roll evidence;
- success/partial/failure outcome;
- stamina/mana/item costs;
- injury/condition effects;
- retreat, surrender, interruption, unconsciousness, and death paths;
- bounded beat budget;
- atomic scene commit.

Narration receives the committed resolution. It cannot change injury severity, invent attacks, or continue combat beyond the beat budget.

## 7. Magic

A spell definition includes:

- stable ID/version;
- affinity/school tags;
- prerequisites and known-by records;
- cast time, target/range/area;
- mana/material/focus costs;
- expected effects and allowed effect types;
- concentration/channel/activity behavior;
- failure modes and counters;
- visibility and sensory signatures.

Models may propose creative use of known magic. Validators map it to feasible effects. Unknown spells, free resource creation, impossible range, and undeclared targets are rejected or repaired.

## 8. Activities, travel, and quiet phases

Activities support:

- start, duration, progress, resource use, completion, and interruption;
- travel, rest, training, work, crafting, recovery, research, and rituals;
- deterministic continuation without a model call when no decision is needed.

Travel uses explicit routes, duration, terrain/weather modifiers, travel mode, and optional encounter candidates.

Quiet phases should frequently resolve without Director or character-model calls. This is a quality, cost, and world-coherence feature.

## 9. NPC resolution

NPC lifecycle classes:

- background extra;
- temporary named;
- recurring supporting;
- lineage character.

Only the Director normally proposes new NPC identities. Deterministic budgets limit creation by scene, region, and day. Entity registration deduplicates identity before any NPC becomes canonical.

Temporary NPCs do not automatically receive full memories, graphs, or focus slots. Importance controls persistence resolution, not model enthusiasm.

## 10. Director and narrative arcs

Director proposals declare:

- narrative purpose;
- prerequisites;
- intended participants and visibility;
- allowed effect categories;
- expected duration;
- pacing/trope tags;
- expiry and cooldown;
- whether rejection is acceptable.

The Director normally acts only on triggers such as stagnation, unresolved consequences, scheduled hooks, arc timing, user direction, or major world changes. Characters may reject the opportunity. The Director adapts rather than forcing the expected plot.

## 11. Narrative quality system

Track deterministic indicators:

- repeated phrases and dramatic constructions;
- repeated locations and participant combinations;
- emotional-shape repetition;
- recent trope usage and cooldown;
- romance evidence and reciprocity;
- Director intervention frequency;
- NPC creation rate;
- unresolved promises/hooks;
- exposition density;
- quiet-to-disruptive phase balance.

Evaluators and human review score:

- causal coherence;
- character voice distinctness;
- agency preservation;
- perspective correctness;
- unsupported narration facts;
- consequence quality;
- romance pacing;
- non-cringe style;
- scene engagement.

Do not turn all stylistic preferences into hard deterministic rejection rules. Hard rules protect canon, safety, and perspective; evaluators guide prompt/profile iteration.

## 12. Visual state

Character and location appearance are structured and versioned.

Character visual state may include:

- physical identity traits;
- hair, eyes, body/build, distinctive marks;
- current age band;
- outfit and equipment;
- injuries visible to the audience;
- expression/pose presentation hints;
- reference asset IDs.

Location visual state may include environment, architecture, season, weather, time of day, lighting, occupancy, and stable landmarks.

Presentation hints such as pose and expression are not canon unless separately represented by a committed observable effect.

## 13. Image pipeline

```text
Committed event marked visually salient
 -> transactional outbox message
 -> image job with idempotency key
 -> load event and versioned permitted visual facts
 -> compose structured image specification
 -> render provider-specific prompt
 -> image gateway
 -> optional quality/continuity checks
 -> store asset metadata and object reference
 -> publish projection update
 -> UI places asset into original historical scene
```

Rules:

- never generate a canonical scene image from an uncommitted proposal;
- image generation never blocks phase completion;
- retries return/reuse the same logical job;
- stale visual-state versions do not overwrite current portrait defaults;
- historical images remain linked to the visual versions used when generated;
- an image cannot introduce a fact into world state;
- manual regeneration creates a new asset candidate, not a rewritten event;
- failures retain structured fallback presentation.

## 14. Asset strategy

Use two image classes:

1. Reusable visual-novel assets: portraits, expressions, outfits, location backgrounds.
2. Salient event illustrations: occasional scene CGs for important committed events.

Routine scenes should compose reusable assets. Generating an image for every line is expensive, slow, visually inconsistent, and unnecessary.

Stage 2 uses curated static fixture assets while validating the UI. Stage 3 introduces provider-neutral remote image generation. Stage 4 adds a versioned ComfyUI workflow on local image hardware.

## 15. Pixel-art consistency

Version visual style packs containing:

- positive and negative style instructions;
- resolution/aspect targets;
- palette and lighting guidance;
- character reference strategy;
- background composition rules;
- sprite/portrait/event-image categories;
- provider/workflow compatibility;
- evaluation fixtures.

Persist the style-pack version and workflow/model identifiers with every asset. Avoid treating one giant prose prompt as the appearance database.

## 16. PixelSaga inspiration boundary

Useful inspiration from `../perchance-ver/`:

- visual novel layout;
- suggested and custom actions;
- scenario/character creation concepts;
- portrait/background/event image layers;
- outfit continuity;
- histories, lore, maps, inventory, and quests;
- regeneration and fallback UX;
- repetition/cliche defenses.

Do not reuse its browser-global state, Perchance plugin APIs, prompt-tag mutation protocol, save compatibility, streaming mutation order, or partially connected D&D tag handling.

The bundled `dnd-data/` is not automatically approved product content. Verify each source, license, attribution obligation, and SRD compatibility before reuse or redistribution.

## 17. Content policy

Default allowed content includes danger, injury, death, grief, betrayal, oppression, moral conflict, non-graphic horror, and implied adult relationships between adults.

Default prohibited content includes explicit sexual content, sexualized minors, sexual violence, fetishized abuse, romantic coercion presented as desirable, prolonged graphic torture, and gratuitous cruelty without consequence.

Policy enforcement belongs at seed validation, user input, model gateway, output validation, and image pipeline boundaries. A safety filter may reject content but must not silently rewrite canonical outcomes.

## 18. Promotion gates

A rules/content subsystem is promotable only when:

- definitions are versioned and schema-valid;
- deterministic validators and effect types exist;
- failures and fallbacks are specified;
- seeded scenarios cover success, partial, failure, invalid, and duplicate paths;
- perspective consequences are generated;
- source event/provenance links exist;
- narration cannot override results;
- content license and attribution are recorded;
- its UI reads backend projections rather than duplicating rules.