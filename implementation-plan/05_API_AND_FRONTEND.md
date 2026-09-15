# API and Frontend Plan

**Status:** Normative interface and presentation design

## 1. Boundary principle

FastAPI exposes typed commands and perspective-aware read models. Vue owns presentation state only. Neither HTTP handlers nor frontend components implement authoritative world rules.

```text
Vue action
 -> generated API client
 -> FastAPI DTO validation and role authorization
 -> application command
 -> run/task identifier
 -> event cursor updates
 -> perspective-safe read projection
 -> Vue rendering
```

## 2. API conventions

- Prefix public application endpoints with `/api/v1`.
- Use UUID strings for IDs and ISO-8601 UTC for operational timestamps.
- Represent fictional time through typed calendar fields and absolute phase index.
- Require `Idempotency-Key` for every state-changing command.
- Require expected aggregate/world version in command payloads where stale writes are possible.
- Return stable machine error codes plus human-readable details.
- Use cursor-based event pagination, never page-number semantics for live timelines.
- Generate and commit OpenAPI plus TypeScript client/types with contract changes.
- Never expose ORM structures directly.
- Player-scoped endpoints cannot request an `omniscient=true` flag.

## 3. Command response shape

Accepted asynchronous command:

```json
{
  "command_id": "uuid",
  "run_id": "uuid",
  "status": "accepted",
  "world_version": 17,
  "event_cursor": 104
}
```

Completed idempotent replay may return the original canonical result:

```json
{
  "command_id": "uuid",
  "run_id": "uuid",
  "status": "completed",
  "result": {
    "event_ids": ["uuid"],
    "world_version": 18,
    "event_cursor": 109
  },
  "idempotent_replay": true
}
```

Error envelope:

```json
{
  "error": {
    "code": "STALE_WORLD_VERSION",
    "message": "World state changed before the command could commit.",
    "request_id": "uuid",
    "details": {
      "expected": 17,
      "actual": 18
    }
  }
}
```

Do not expose stack traces or provider secrets.

## 4. Initial endpoint evolution

### Stage 0

```text
GET  /api/v1/health/live
GET  /api/v1/health/ready
GET  /api/v1/world
GET  /api/v1/world/clock
GET  /api/v1/world/phases/current
GET  /api/v1/world/events?after=<sequence>&limit=<n>
POST /api/v1/world/seed
POST /api/v1/world/phases/advance
POST /api/v1/operations/reconcile
GET  /api/v1/operations/tasks/{task_id}
```

CLI commands provide equivalent seed, advance, inspect, and reconcile behavior for the Stage 0 gate.

### Stage 1

```text
GET  /api/v1/characters
GET  /api/v1/characters/{id}
GET  /api/v1/characters/{id}/perspective
GET  /api/v1/scenes/{id}
GET  /api/v1/scenes/{id}/narration
POST /api/v1/player/intents
POST /api/v1/simulation/pause
POST /api/v1/simulation/resume
GET  /api/v1/model-runs/{id}
GET  /api/v1/context-manifests/{id}
```

Debug trace routes require explicit debug/Watcher permissions.

### Stage 2

```text
GET  /api/v1/timeline
GET  /api/v1/map
GET  /api/v1/characters/{id}/diary
GET  /api/v1/characters/{id}/relationships
GET  /api/v1/characters/{id}/goals
GET  /api/v1/operations/queue
POST /api/v1/director/proposals
POST /api/v1/deity/overrides
POST /api/v1/roles/select
POST /api/v1/mode/select
```

### Stages 3-5

Add encyclopedia, long-term memory inspection, image jobs/assets, evaluation reports, provider status, macro simulation, genealogy, end-condition evidence, export, and restore APIs only when their stages implement them.

## 5. Query scopes

Use separate application query services and response DTOs:

- `OmniscientWorldQuery`: Watcher/debug only;
- `CharacterPerspectiveQuery(observer_id, as_of_sequence)`;
- `PlayerViewQuery(controlled_character_id)`;
- `PublicWorldQuery`: facts considered publicly known in-world;
- `OperationsQuery`: task/model/image health with fictional content redaction;
- `TimelineQuery(audience, cursor)`;
- `MapQuery(observer)`;
- `EncyclopediaQuery(observer)`.

Do not fetch omniscient records and filter them in Vue.

## 6. Realtime protocol

REST owns command submission. WebSocket publishes server-originated updates needed by automatic simulation and job completion.

Connection flow:

1. Client loads a read projection and last event cursor through REST.
2. Client connects with `after=<cursor>`.
3. Server replays retained envelopes after that cursor, then streams new envelopes.
4. Client discards duplicates and applies messages only in sequence order.
5. On gap or retention miss, client refetches the affected projection.

Envelope:

```json
{
  "sequence": 109,
  "kind": "scene.narration.ready",
  "world_id": "uuid",
  "phase_run_id": "uuid",
  "entity_id": "uuid",
  "projection_version": 18,
  "occurred_at": "UTC timestamp",
  "payload": {}
}
```

The event stream is a notification channel, not canonical storage. Clients recover through read APIs.

## 7. Vue application structure

```text
src/
  api/                 generated client, transport, error mapping
  components/          genuinely reusable presentation components
  features/
    shell/
    timeline/
    visual-novel/
    characters/
    player-control/
    map/
    encyclopedia/
    diary/
    operations/
    settings/
  routes/
  stores/              session, UI preferences, selected IDs, cursors
  styles/              reset, tokens, themes, typography, layouts
  assets/
```

Frontend stores may own:

- selected route/tab/entity;
- open drawers/dialogs;
- theme and reduced-motion preference;
- current event cursor and connection status;
- provisional command submission status;
- local form drafts;
- image loading/presentation state.

Frontend stores may not own:

- character inventory/resources;
- event outcomes;
- skill progression;
- relationships or beliefs;
- phase status;
- rule calculations;
- canonical retry decisions.

## 8. UI design workflow

Before implementing any nontrivial real Vue screen or visual change:

1. Build two or more distinct static HTML mocks with embedded vanilla JavaScript.
2. Use realistic fixture data and exercise desktop/mobile layouts.
3. Present the mocks for product-owner selection.
4. Stop before changing production Vue components.
5. After a direction is selected, encode tokens/layout and implement the chosen surface.
6. Verify the actual browser surface at target viewports.

Standing visual constraints:

- true dark mode uses `#000` as the main canvas;
- true white mode is genuinely white rather than light gray;
- information-dense layouts;
- minimal copy;
- no decorative card/pill chrome as a default layout device;
- no light-gray eyebrow subtitles above sections;
- no continuously repainting pulse, shimmer, blur, or spinner animations;
- reduced-motion mode is first-class.

## 9. Visual-novel scene model

A client scene projection contains:

- committed event and scene IDs;
- fictional time and location;
- audience/perspective identifier;
- ordered narration beats;
- visible participants and versioned visual-state references;
- selected background/portrait/expression assets;
- optional salient-event image status;
- player action state when applicable;
- links to source events without exposing hidden facts.

Narration beats may render as narrator text, dialogue, action, system/result, or transition. Speaker identity is an entity ID, not a free-form name.

If narration is delayed or failed, show concise structured event text. Do not hold canon hostage to prose generation.

## 10. Primary routes

Planned routes:

```text
/                         current timeline/visual novel
/characters               focus cast
/characters/:id           permitted card, state, history, diary
/map                      role-filtered world map
/encyclopedia             known world records
/timeline                 searchable committed events
/operations               phase/task/model/image status
/settings                 model, budgets, content, accessibility
/debug/traces             Watcher/debug-only context and model traces
```

Avoid deep modal stacks. Routes represent durable navigation; drawers/dialogs handle short contextual tasks.

## 11. Player interaction

At a safe player decision boundary, show:

- the controlled character's current perception;
- own relevant state/resources;
- suggested intents generated from that perspective;
- free-form intent and optional dialogue;
- action family, targets, and desired effects when useful;
- explicit notice that the player controls an attempt, not its result.

Submission creates one idempotent command. Disable duplicate local submission for usability, while backend idempotency remains authoritative.

## 12. Operations and debug UX

Expose:

- current world/phase state;
- pause/resume/manual-step controls;
- task graph, attempts, leases, and terminal errors;
- model profile, latency, tokens, repairs, and fallbacks;
- context manifest source metadata;
- scene resolution and accepted effects;
- outbox/image queue status;
- retry/skip controls permitted by task type;
- consistency audit results.

Do not expose hidden character content when the active session is player-scoped.

## 13. Accessibility

- Semantic headings, landmarks, buttons, labels, and dialog behavior.
- Full keyboard access and visible focus.
- Escape/return-focus behavior for dialogs.
- Text alternatives for generated images based on committed visible facts, not image hallucinations.
- Configurable text size, line width, contrast, and dialogue pacing.
- Reduced motion disables nonessential transitions and automatic typewriter effects.
- Screen readers receive completed text rather than rapidly changing token fragments.
- Color never carries outcome, relationship, or injury meaning alone.

## 14. Frontend verification

For each implemented surface:

- run against the real API or a contract-faithful fixture server;
- verify dark and white modes;
- verify desktop and narrow mobile viewport;
- verify keyboard-only operation;
- verify reconnect/cursor replay;
- verify stale projection conflict presentation;
- verify delayed/failed narration and image states;
- confirm no frontend code computes canonical outcomes;
- use Playwright only for durable user contracts, not visual implementation trivia.