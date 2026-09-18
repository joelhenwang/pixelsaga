# A00 baseline (19 September 2026)

## Checkout

- HEAD `01655f9` (`ui revamp tests`), matches the reviewed SHA in the plan. No rebase needed.
- Tree clean except untracked planning docs (`docs/pixelsaga-mainmenu/`, three revamp planning files). No user work to preserve beyond leaving those alone.
- Migration head: `0029_revamp_conditions` (0027 assets, 0028 interventions landed in order).
- Style records: `content/visual-styles/anime-saga-v1.json` is the runtime style; `pixel-saga-v1.json` preserved untouched.
- Starter art present: `content/assets/revamp/wren-portrait-v1.png`, `ash-portrait-v1.png`, Ember Vale manifest + map.

## Confirmed blockers (source-verified, not carried claims)

1. **First-world selection**: `backend/src/worldsim/interfaces/http/routes/world.py:50-56`
   `_only_world()` returns `worlds[0]` for `/world`, `/world/clock`, `/world/phases/current`,
   `/world/events`. Multi-story reads are impossible until these take a validated `world_id`.
2. **First-character auto-bind**: `frontend/src/store.ts:114-116` sets
   `characterId` to `list[0].id` when unbound. Must become explicit repair/selection UI.
3. **Director/Deity mismatch reproduced** (throwaway `backend/tests/test_a00_repro.py`,
   since removed): plain director/deity `POST /api/v1/stage1/advance` (no intents) and
   director `GET /api/v1/simulation/status` all return
   `403 FORBIDDEN "director/deity cannot use this command"`.
   Cause: `stage1.py:76` `require_role(role, "watcher", "player")` inside
   `_perspective(request, world_id)` fires before the capability check, even though
   `application/capabilities.py:39-58` grants DIRECTOR and DEITY `ADVANCE`.
   `stage1.py:307-310` (directed attempts go through the queue) is currently dead code.
   Existing P03 tests only assert the with-intents 403, so the suite stays green.
4. **Stale async writes**: `store.ts` reads carry a `sessionKey` guard, but
   `useSimulationControl.ts` playback (`playToken`) reads mutable global `worldId`
   after awaits, and `switchRole()` never invalidates the token. A02 must bind
   immutable `{storyId, worldId, role, characterId, epoch}` and tear down
   playback/listeners/timers on story leave.
5. **Seed cannot mint stories**: stable literal IDs, idempotent `import_seed`
   (`application/commands/seed_world.py`). A06 needs a separate instantiation
   service with fresh IDs, not another seed call.
6. **Frontend routes**: `/` redirects to `/scene`; eight gameplay views plus
   `/adventure` and `/world` redirects (`frontend/src/router.ts:14-24`). No shell yet.

## Section 0 decisions: confirmed as written

One story = one runtime World (UUID as storyId); single-operator installation first
(bearer key is not user identity); database-backed drafts/presets; pinned resolved
setup snapshots; archive before deletion; fake/OpenRouter text paths only, no live
image adapter prerequisite. No checkout evidence contradicts these; no adjustment.
## Baseline verification

- Full backend suite on disposable `migrated_db` fixtures: 489 collected
  (486 repo + 3 throwaway repro), all green, one skip. Repro file removed
  after recording; its assertions become real A02 regression tests.
- No dev-save database touched. Scratch stack uses a disposable DB when A01/A10 need it.
- Pre-existing `make migration-status` relationship drift noted in plan; rechecked in A10.
