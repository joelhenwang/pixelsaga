# Revamp release handoff (P11, 18 September 2026)

## What shipped

Adventure Journal and World Observatory replace the dev harness,
backed by capability policy, presentation/chronicle contracts, an
asset pipeline with curated starter art, single-writer execution
admission, a durable intervention queue, linked character creation,
and persistent world conditions. Packets P00–P10 are committed;
P11 is this verification.

## Capability table (enforced server-side)

| Capability | Watcher | Director | Deity | Player |
|---|---|---|---|---|
| Omniscient reads | yes | yes | yes | own perspective |
| Advance/pause | yes | yes | yes | advance only |
| File attempts | no | no | via queue | own only |
| Propose hooks/arcs | no | yes | yes | no |
| Force activities/overrides/conditions | no | no | yes | no |
| Player custom attempts | no | no | no | bound actor, attempt mode |
| Macro advance/compose/evaluate/assign | yes | yes | yes | no |
| Character creation | yes | yes | yes | yes |

Watcher filing attempts is rejected (was allowed). Director activity
writes are rejected (propose instead). Player activity writes are
limited to their own character. Macro advance rejects while any
world condition is active.

## Endpoints added

- `GET /api/v1/world/presentation`, `GET /api/v1/world/chronicle`
- `GET /api/v1/simulation/status`
- `POST /api/v1/stage1/characters`, `POST /api/v1/stage1/party/{id}/link`
- `GET /api/v1/stage1/suggestions?character_id=`
- `POST /api/v1/assets/jobs`, `GET /api/v1/assets/jobs/{id}`,
  `POST /api/v1/assets/ensure-starter`, `GET /api/v1/assets`,
  `GET /api/v1/assets/{id}`
- `POST /api/v1/interventions`, `GET /api/v1/interventions`,
  `GET /api/v1/interventions/{id}`, `PATCH /api/v1/interventions/{id}`,
- `POST /api/v1/interventions/{id}/cancel`
- `GET /api/v1/world/conditions`

## Migrations (all additive, landed in order)

- `0027_revamp_assets`: asset_record, image_job.
- `0028_revamp_interventions`: intervention, intervention_step.
- `0029_revamp_conditions`: world_condition plus `condition_tick`
  in `ck_event_type`.
- Dev database upgraded 0026 → 0029 in place; saves preserved
  (verified: worlds intact, head `0029_revamp_conditions`).
- Rollback: disable the new UI/routes and run compatible code.
  Do not downgrade data-bearing migrations.

## Verification

- `make lint`, strict `basedpyright`, `make contracts`: clean.
- Full backend suite: 486 collected, all green (one skip).
- `verify.mjs`: 12/12 green on a scratch stack (fresh DB),
  including the player action round trip through the queue.
- Production `web` image builds (`docker compose build web`) and
  serves the bundle with `/api` proxied; SPA fallback enabled.

## Known limitations (honest)

- No live text/image provider is configured. The interpreter runs
  on the injected gateway (fake → clarification); image jobs
  complete explicitly through the fixture seam. Curated starter
  art ships instead.
- No rendered screenshots in this handoff: verification is
  Playwright assertions, not captured images.
- Seeded worlds carry no TravelRoute rows (pre-existing gap), so
  travel suggestions and directed travel need legs added out of
  band; journey tests seed their own.
- `make migration-status` reports unmigrated `relationship`
  table drift (pre-existing, P00 baseline). Unrelated to revamp
  tables; still open.
- Crash-after-effect-commit windows rely on step-key recovery
  checks (activities, hooks) or re-drive; override re-drive may
  mark failed rather than double-apply.
- Per-turn scene art generation is not implemented; scenes share
  world background art until the P04 job pipeline gains a live
  adapter with cost caps.
