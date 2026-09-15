# Execution Control and Delivery Protocol

**Status:** Normative project execution process

## 1. Purpose

Convert the staged architecture into reviewable work without parallel agents or developers creating conflicting contracts, migrations, or canonical writers.

## 2. Work hierarchy

```text
Product decision
 -> Stage
 -> Capability
 -> Task packet
 -> Implementation changes
 -> Focused behavioral evidence
 -> Stage scenario/gate
 -> Promoted version
```

The stage documents define required outcomes. Task packets define ownership and acceptance. Implementation details may change if they preserve those contracts.

## 3. Task identity

Use stable IDs:

```text
S<stage>-<area>-<number>
```

Examples:

- `S0-TX-001`
- `S1-CTX-001`
- `S3-IMAGE-001`

Do not recycle an ID for different work. Split a task only when the original acceptance criteria and dependency links are updated.

## 4. Task states

```text
PROPOSED
-> READY
-> IN_PROGRESS
-> REVIEW
-> VERIFIED
-> COMPLETE
```

Exceptional states:

- `BLOCKED`: external decision or unavailable prerequisite;
- `FAILED`: implementation/evidence failed and needs revision;
- `DROPPED`: explicitly removed from stage scope with reason;
- `SUPERSEDED`: replaced by named task/decision.

Only tasks whose dependencies and input contracts are frozen may become READY.

## 5. Task packet template

Every implementation task states:

```text
ID and title
Stage capability and user-visible purpose
Dependencies
Owned files/symbols/migrations
Shared contracts consumed
Exact behavior to implement
Canonical data read/write scope
Idempotency and expected-version semantics
Failure/retry/fallback behavior
Perspective and permission rules
Explicit non-goals
Focused verification scenario
Observable acceptance criteria
Generated artifacts/docs affected
Handoff outputs
```

One-line tasks without acceptance criteria are not executable.

## 6. Ready criteria

A task is READY only when:

- all strict dependencies are complete;
- required schema/port/DTO versions are named;
- owned mutation boundary is unambiguous;
- no concurrent task owns the same migration or canonical writer;
- fixture inputs exist or are part of the task;
- failure and duplicate semantics are understood;
- product decisions needed by the task are resolved.

## 7. Implementation sequence

For each task:

1. Read the stage packet and relevant contracts.
2. Inspect existing patterns and affected references before exported-symbol changes.
3. State ownership, invariants, and non-goals.
4. Reproduce or run the named pre-change scenario when applicable.
5. Implement the smallest complete behavior.
6. Remove superseded code and alternate writers in scope.
7. Run the focused behavioral scenario.
8. Run affected architecture, migration, type, and contract checks.
9. Review as the user: clarity, failure behavior, inspectability, and unnecessary complexity.
10. Update generated artifacts and relevant plan/status records.
11. Mark REVIEW only with concrete evidence.

Do not stop at a phase boundary, scaffold, route shell, or unexercised table.

## 8. Parallel work rules

Parallelize only genuinely independent ownership:

- pure domain rules versus provider adapters;
- seed content versus test harness after schemas freeze;
- read-only frontend mocks versus backend implementation using frozen fixture DTOs;
- distinct graph roles after shared graph/context contracts freeze.

Serialize:

- Alembic migration ownership;
- shared domain contract changes;
- canonical transaction service changes;
- generated OpenAPI/client refresh;
- stage evidence integration.

Cross-task interface contracts are agreed before parallel implementation. Siblings do not invent incompatible DTOs and reconcile them after coding.

## 9. Migration ownership

One task owns the active migration chain. Other tasks request schema changes through that owner or wait for the migration contract.

A schema task publishes:

- migration revision;
- affected tables/constraints/indexes;
- domain and DTO versions;
- fixture upgrade result;
- rollback/forward-fix policy.

No application task creates tables dynamically.

## 10. Model and graph change workflow

1. Define or update structured input/output schema.
2. Define deterministic validators and fallback.
3. Run actual graph/model output on representative fixture and inspect its shape.
4. Freeze run-function output shape.
5. Add or update dataset examples/evaluators.
6. Change prompt/profile/graph.
7. Run fake deterministic contract scenarios.
8. Run local evaluation dataset.
9. Optionally run capped live-provider experiment.
10. Compare against current promoted version.
11. Promote a new prompt/profile/graph version only with traceable evidence.

Do not adjust evaluators merely to make a worse output pass.

## 11. UI change workflow

For every nontrivial UI/layout/copy direction:

1. Build at least two distinct static HTML plus vanilla JavaScript mocks.
2. Use realistic API fixture data.
3. Demonstrate dark/white, desktop/mobile, loading/error/empty, and reduced-motion states.
4. Present the alternatives and stop.
5. Record product-owner selection.
6. Implement only the selected direction in Vue.
7. Verify the actual browser surface and interaction.

A mock is disposable decision support, not production architecture.

## 12. Review checklist

### Correctness

- Which source owns the changed data?
- Can duplicate or stale work apply twice?
- Are remote calls outside transactions?
- Does failure leave a valid recoverable state?
- Are all effects sourced and versioned?

### Perspective/security

- What data can this role/actor see?
- Are mandatory filters applied before retrieval?
- Can untrusted content alter instructions/tools/effects?
- Are secrets or hidden fictional facts logged/exposed?

### Architecture

- Does domain remain framework-independent?
- Is there a second writer/source of truth?
- Does a graph or frontend contain business authority?
- Is the abstraction required and exercised now?
- Can provider/infrastructure adapters be replaced through the existing port?

### Product

- Does the behavior preserve agency and causal simulation?
- Can quiet/failure outcomes remain meaningful?
- Does the UI explain status without exposing hidden facts?
- Is the change inspectable six months later?

### Verification

- Does each permanent test defend a real contract?
- Was the actual runtime surface exercised?
- Were migration/fault/duplicate paths run where relevant?
- Are evidence claims limited to what was executed?

## 13. Change control

### Product decision

Required for changes named in [01_PRODUCT_CHARTER.md](01_PRODUCT_CHARTER.md), including 5e rules, multiple worlds, public sharing, focus slots, calendar, canon ownership, or content policy.

### Architecture decision

Required when changing database authority, graph/global orchestrator boundary, event/projection strategy, provider boundary, deployment topology, or frontend framework.

Decision record contains:

```text
ID and status
Problem and constraints
Decision
Alternatives considered
Consequences
Migration/rollback effect
Stage and gate changes
Revisit trigger
```

Small implementation choices that preserve existing contracts do not need a decision record.

## 14. Contract/version policy

Version when compatibility or historical interpretation matters:

- commands, effects, events, exports;
- prompts/model profiles;
- context envelopes/manifests;
- seeds/content definitions;
- visual state/workflows;
- API paths/DTOs;
- embeddings and retrieval configuration;
- evaluation datasets/evaluators.

Internal refactors do not create artificial public versions.

## 15. Generated artifacts

Regenerate only through repository commands:

- OpenAPI and frontend client/types;
- domain JSON Schemas;
- database schema diagrams/dumps;
- prompt/profile manifests;
- content validation reports;
- stage evidence indexes.

Generated files identify source version and are not edited manually.

## 16. Stage status record

Maintain a concise status table in this handbook index or a dedicated generated status file once implementation starts:

| Task | State | Owner | Dependencies | Evidence | Notes |
| --- | --- | --- | --- | --- | --- |

Status updates describe verified behavior, not percentage guesses. Avoid calendar estimates in the execution contract; sequence and acceptance determine readiness.

## 17. Stage integration order

1. Merge/freeze domain and boundary contracts.
2. Apply one owned migration chain.
3. Merge repositories and pure rules.
4. Merge transaction/task infrastructure.
5. Merge seed and fake-driven orchestration.
6. Merge model/graph roles.
7. Merge API/generated client.
8. Select UI mock and merge Vue surface.
9. Run stage scenario, fault matrix, consistency audit, and evidence generation.
10. Promote versions and tag/archive evidence.

## 18. Handling unexpected findings

When implementation reveals a false assumption:

- stop only the affected task, not unrelated lanes;
- preserve evidence and exact failing contract;
- determine whether the issue is implementation, task packet, architecture, or product scope;
- update the smallest authoritative document;
- revise dependent task acceptance criteria;
- do not hide the discrepancy with a compatibility shim or permissive parser.

## 19. Initial action queue

Execute Stage 0 in this order:

1. `S0-BOOT-001` repository bootstrap.
2. `S0-CONFIG-001` and `S0-QA-001` after bootstrap.
3. `S0-DOM-001` domain contracts.
4. `S0-DB-001` database/Alembic baseline.
5. Continue according to [08_STAGE_0_EXECUTION.md](08_STAGE_0_EXECUTION.md).

Do not create Vue production components, autonomous graphs, or broad world content before the Stage 0 deterministic commit proof.

## 20. Completion policy

A task cannot be called complete with placeholders, TODO implementations, no-op fallbacks presented as real behavior, or unrun acceptance scenarios. A stage cannot be promoted while actionable hard-gate work remains.

The final evidence must show the system doing the promised behavior, not merely tests asserting a scaffold exists.