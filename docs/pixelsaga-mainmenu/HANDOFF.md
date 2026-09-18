# Mainmenu handoff: application pages and story-aware routing (A00–A10)

## What shipped

Five application pages around the existing Adventure Journal and World
Observatory, backed by story-aware reads, a catalog with immutable setup
snapshots, database drafts, revisioned presets, a provider pipeline, atomic
creation, and archive enforcement.

- **Home** (`/`): continue hero (last explicitly opened story), new-tale
  card, library card with world/character minis. Empty DB shows Begin your
  first tale; opening Home never seeds, advances, or calls a model.
- **New Story** (`/new-story?draft=&step=`): world, cast, mode, story, AI,
  review. Cast before mode; Player binds a cast member; Watch reveals
  Observer/Director/Deity. Explicit saves, two-tab 409 recovery, reload
  resume, Quick Start prefill, stable idempotency keys in localStorage.
- **Stories** (`/stories`): status filter, search, cursor pagination,
  read-only setup modal (focus trap, Esc, Back-or-replace close, legacy
  unknown-honest), card menu with rename, export, use-as-new-story,
  archive/unarchive with confirmations.
- **Library** (`/library`): worlds and characters simultaneously with a
  gold divider; editor with dirty guard; revisions never rewrite; built-ins
  read-only (duplicate first); archive preserves referenced art; style packs
  and templates in a disclosure.
- **Settings** (`/settings?section=`): providers (write-only credential
  references, explicit bounded probes), model revisions with supported
  sampling only, honest unavailable images, gameplay defaults, classified
  cache reset, accessibility, advanced diagnostics.
- **Story shell** (`/stories/:storyId/...`): validated entry, saved-grant
  binding, epoch-voided stale work, playback teardown on leave, ended-story
  banner with disabled advance. Legacy bookmarks resolve explicitly: one
  story redirects, many ask, none routes to the catalog.

## Capability and behavior notes

- Director/Deity plain advance, status, pause, and resume now follow the
  capability table (A02 fixed the `_perspective` blanket rejection).
- Archived stories reject advance, pause/resume, macro, activities, party
  writes, proposals, overrides, image jobs, and queued admission (409 with
  `PRECONDITION_FAILED`); claim-time row locks make the boundary atomic.
- Draft payloads, setup snapshots, exports, traces, and URLs never carry
  secrets. Provider credentials live only as environment references.
- Pinned profile revisions resolve once per phase run into sampling params
  threaded through all six model graphs; unpinned stories use process env.

## Migrations (all additive, landed in order)

- `0030_application_shell`: story_catalog, story_initial_setup, story_draft,
  preset, preset_revision, story_creation_receipt; backfills one catalog row
  plus a legacy-unknown setup per world; imports five Ember Vale built-ins.
- `0031_settings_pipeline`: provider_connection, provider_profile_revision,
  application_preferences.
- Dev database upgraded 0029 → 0031 in place (backed up before each step);
  saves preserved. Rollback: disable the new UI/routes and run compatible
  code. Never downgrade data-bearing migrations.
- `alembic check` still reports the pre-existing metadata-import drift
  (remove-only artifact, documented in the mainmenu plan); A03/A05 tables
  introduce no new drift kinds.

## Verification

- Full backend suite: 515 collected, all green (two skips).
- `make lint` on touched files, strict `basedpyright` (one pre-existing
  interleave unused-variable error remains), `make contracts` clean.
- `frontend/verify.mjs`: 15/15 green on a disposable stack (fresh DB,
  API :8101, vite :5175), covering empty home through wizard creation,
  player action round trip, setup modal, theme, mobile, clean console.
- Production `vite build` succeeds. Desktop and 390px screenshots of all
  five pages reviewed against the approved static mocks.

## Known limitations (honest)

- No live text/image provider is configured. Fake mode is labeled demo;
  explicit live probes report unwired spend instead of spending.
- Player scene strip is viewer-filtered by design: a player only sees
  scenes their character joins.
- No automatic party seating at creation; the grant binds the actor and
  PartyView links later. No full-party auto-seat, no duplicate identities.
- Setup export is redacted configuration, not a save backup. Full saves
  travel with the database process.
- An archive racing an already-claimed slot lets that single in-flight
  phase finish; no new work admits afterwards.
- Per-turn scene art still awaits a live image adapter with cost caps.
