# Operations, Security, and Recovery Plan

**Status:** Normative operational design

## 1. Initial operating profile

- One local user.
- FastAPI binds to `127.0.0.1` by default.
- PostgreSQL runs in a local container with persistent volume.
- One application process initially owns API, orchestration, and in-process workers.
- Vue dev server is separate during development; production build is served by FastAPI or an equivalent single local origin.
- Remote model/image/LangSmith services are opt-in through configured adapters.
- No public Internet listener or public sharing service is part of initial scope.

## 2. Configuration groups

Typed settings:

- application/version/environment;
- HTTP host/port and allowed origins;
- PostgreSQL connection/pool/timeouts;
- model gateway profiles, keys, quotas, and timeouts;
- LangSmith enabled/project/endpoint/redaction;
- worker leases, attempts, and concurrency;
- embedding dimensions/versions;
- image gateway/storage/workflows;
- content and narrative policies;
- logging and retention;
- backup/export paths;
- debug and role capabilities.

Validate settings at startup. Reject unsafe combinations such as public bind without explicit authentication, invalid embedding dimensions, missing active model profile, writable export path outside configured roots, or production tracing without a redaction policy.

## 3. Secret handling

Secrets include database passwords, OpenRouter/provider keys, LangSmith keys, object-store credentials, and future service tokens.

Rules:

- never commit secrets;
- provide `.env.example` names only;
- load through environment or approved local secret mechanism;
- never store secrets in world events, model profiles, graph state, context manifests, prompts, API responses, generated OpenAPI, or evidence bundles;
- redact known values and credential-shaped fields from logs;
- do not pass provider credentials through Vue;
- rotate a credential after suspected log/export exposure;
- tests use synthetic sentinel secrets and assert absence from all captured output.

## 4. Trust boundaries and threats

### Untrusted model output

Parse through strict schema, reject unknown fields/effects, validate permission/knowledge/resources/versions, and never expose repository write tools.

### Prompt injection in fictional data

Memory, lore, dialogue, seed content, imported content, and user free text remain delimited data. They cannot change system instructions, tool scope, role permissions, or effect vocabulary.

### Perspective leakage

Enforce owner/visibility/as-of filters in application/SQL queries before retrieval. Do not rely on prompts or frontend hiding.

### Imports and restores

Apply size/depth/count limits, strict versions, checksums, reference validation, path restrictions, and temporary-schema verification. Never deserialize executable objects.

### Generated assets

Validate media type, dimensions, size, checksum, storage key, and source job. Do not trust filenames or model-supplied paths. Serve assets with appropriate content types and no script execution.

### API and WebSocket

Validate origin and session/role scope. State-changing commands require idempotency. WebSocket messages contain only permitted projections and reconnect cursors.

### Database

Use parameterized ORM/SQL, least-privilege application role, migrations through a separate controlled path where practical, bounded statement/lock timeouts, and no arbitrary model SQL.

## 5. Logging and audit

Structured logs carry:

- request ID;
- command ID and idempotency key hash/reference;
- world/phase/scene/task/graph/model/event IDs;
- operation name and state transition;
- attempt, lease, latency, status, and stable error code;
- provider/profile without credentials;
- event cursor/version where applicable.

Default logs do not contain full prompts, raw hidden memories, model completions, or private fictional secrets. Debug access to durable model/context records is role-gated and separately auditable.

## 6. Health and readiness

### Liveness

Confirms process event loop is responsive. It does not query all dependencies.

### Readiness

Checks:

- database connectivity;
- expected migration head;
- required extensions;
- seed/world state compatibility;
- orchestrator leadership state;
- required active model profiles and capabilities when the selected mode needs them;
- writable storage paths;
- unrecoverable consistency status.

Optional image, embedding, LangSmith, and noncritical worker outages appear as degraded dependencies but do not necessarily fail textual-simulation readiness.

## 7. Failure behavior matrix

| Failure | Required behavior |
| --- | --- |
| Database unavailable | Do not acknowledge commands/tasks; no in-memory canon; retry connection |
| Crash before canonical commit | Retry task from durable state; no event exists |
| Crash after commit/before acknowledgement | Idempotency lookup returns committed result |
| Expired task worker | New worker reclaims; late worker cannot finalize |
| OpenRouter 429/quota | Honor retry metadata; do not begin unsafe batch; fallback or pause safely |
| Malformed model result | Local extraction/validation, one repair, fallback or visible failure |
| LangSmith unavailable | Continue with durable local trace; queue/drop external telemetry by policy |
| Embedding unavailable | Keep recent relational memory; enqueue retry; do not block unless stage declares retrieval required |
| Image unavailable | Keep job queued/failed; textual canon proceeds |
| WebSocket disconnect | Client reconnects from cursor and refetches projections on gaps |
| Narration unavailable | Show structured committed event fallback |
| Consistency violation | Pause advancement, retain evidence, run audit/rebuild or require intervention |
| Hard retcon | Taint dependent projections, pause as configured, audit before resume |

## 8. Startup reconciliation

On startup:

1. Validate configuration and migration head.
2. Acquire or observe world leadership lease.
3. Detect expired task leases and return eligible work to pending.
4. Inspect nonterminal phase runs.
5. Resolve idempotency records with committed event results.
6. Requeue unacknowledged outbox work.
7. Verify no next phase exists over incomplete prior phase.
8. Run lightweight hard-invariant checks.
9. Refuse automatic advancement if a terminal inconsistency exists.
10. Publish current readiness and recovery summary.

Reconciliation uses durable state, not assumptions about the last process.

## 9. Backup model

### Development

- reproducible seeds and migrations;
- periodic database dump before destructive migration tests;
- local visual assets considered replaceable until Stage 3.

### Promoted stages

Back up:

- PostgreSQL logical dump or verified physical strategy;
- application/migration version;
- seed/content/prompt/profile versions;
- generated schemas;
- object/asset manifest and checksums;
- evaluation/evidence metadata.

Do not claim a backup is valid until restore is tested.

## 10. Restore procedure

1. Stop automatic advancement and new state-changing commands.
2. Record current diagnostic/evidence state.
3. Restore into a new database/schema, never over the only copy.
4. Apply supported migrations.
5. Validate checksums, row counts, foreign keys, event sequences, versions, and hard invariants.
6. Verify asset references and identify safely regenerable missing presentation assets.
7. Run the promoted stage's focused recovery scenario.
8. Atomically switch configured database only after validation.
9. Retain prior database until explicit cleanup.
10. Record restore audit and operator identity.

## 11. Migration operations

- Alembic maintains one head.
- Application startup does not silently apply production migrations.
- Migration command prints source/target revisions and backup prerequisite.
- Migrations are tested against empty and every supported promoted fixture.
- Long data migrations are resumable or staged outside one long lock.
- Destructive migrations require explicit approval and verified backup.
- Unsupported future schemas fail closed.

## 12. Task and queue operations

Expose metrics and commands for:

- pending/running/retry/dead-letter counts by task kind;
- oldest queue age;
- lease owner/expiry and heartbeat age;
- attempts and stable errors;
- retry one eligible task;
- skip only task kinds with defined safe skip semantics;
- pause/resume phase at safe boundary;
- reconcile world;
- inspect outbox delivery.

Manual task changes create operational audit records. Never delete a failed task merely to make a phase appear complete.

## 13. Model and budget operations

Track per role/profile/provider:

- request/token counts;
- estimated and actual cost;
- quota/rate-limit status;
- latency distribution;
- structured validity;
- repair/fallback/error rate;
- active capability probe;
- concurrency and queue wait.

Before a phase starts required concurrent intent work, reserve or verify sufficient budget for a safe completion/fallback plan.

## 14. Data retention

- Canonical events/effects and source provenance are retained.
- Current projections retain source links.
- Operational task/model records retain enough history for promoted-stage audits.
- Full raw prompts/completions may use configurable retention and redaction.
- LangGraph checkpoints are prunable after terminal workflow retention.
- LangSmith retention is external and never the sole audit source.
- Failed/generated images may expire after checks and references prove they are not selected/live.
- Deletion/compaction jobs are idempotent and auditable.

## 15. Local network exposure

Default: loopback only.

Private remote access may later use Tailscale Serve or an equivalent authenticated tunnel. Enabling access requires:

- explicit user authentication/session model;
- server-side role authorization;
- CSRF/origin/WebSocket review;
- secure cookies/TLS at the access boundary;
- rate and request-size limits;
- no provider secrets in client bundles;
- threat review for omniscient/debug routes.

Do not bind `0.0.0.0` as a convenience default.

## 16. Stage 4 worker operations

Local model/image workers expose capability and health through adapters. The control plane owns routing and budgets.

- workers are stateless regarding character identity;
- requests carry task/context/profile IDs, not DB credentials;
- concurrency is bounded per hardware service;
- health loss stops new routing and safely retries eligible work;
- high-volume image/evaluation work cannot starve phase-critical text work;
- local service output remains untrusted.

## 17. Incident runbooks

Maintain executable runbooks for:

- database unavailable;
- migration mismatch/multiple heads;
- stuck phase;
- expired or poisoned task;
- duplicate/idempotency conflict;
- model quota exhaustion;
- perspective leak detected;
- hard invariant failure;
- failed restore;
- missing visual asset;
- worker resource exhaustion;
- accidental secret exposure.

Each runbook states detection, immediate containment, evidence to preserve, safe recovery, validation, and prevention follow-up. Never resolve a consistency incident by manually changing canonical rows without an audited migration or Deity command.