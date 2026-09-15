# PixelSaga Autonomous World Implementation Handbook

**Status:** Execution baseline
**Purpose:** Define the product, architecture, contracts, stage gates, and task sequence for building a local-first autonomous fantasy RPG and visual novel.

## 1. Product in one sentence

Build one persistent fictional world that advances autonomously through deterministic rules and bounded model proposals, while one local user can watch, direct, override, or play a character through a pixel-art visual-novel interface.

PixelSaga at <https://perchance.org/pixelsaga> is a product and interaction reference. `../perchance-ver/` is a searchable idea catalogue. Neither is a compatibility target or a source of canonical architecture.

## 2. Authority order

When documents disagree, use this order:

1. Product decisions and exclusions in [01_PRODUCT_CHARTER.md](01_PRODUCT_CHARTER.md).
2. Invariants and ownership rules in [02_SYSTEM_ARCHITECTURE.md](02_SYSTEM_ARCHITECTURE.md), [03_DOMAIN_AND_PERSISTENCE.md](03_DOMAIN_AND_PERSISTENCE.md), and [04_AI_CONTEXT_AND_TRACING.md](04_AI_CONTEXT_AND_TRACING.md).
3. Stage scope and exit gates in [08_STAGE_0_EXECUTION.md](08_STAGE_0_EXECUTION.md), [09_STAGE_1_EXECUTION.md](09_STAGE_1_EXECUTION.md), and [10_STAGES_2_TO_5_EXECUTION.md](10_STAGES_2_TO_5_EXECUTION.md).
4. Cross-cutting delivery rules in the remaining documents.
5. `../MONOLITH_MIGRATION_REFERENCE.md` only where it does not assume a legacy migration.

A code change must not silently revise an accepted product or architecture decision. Record the change in the relevant document and state its effect on active stage gates.

## 3. Fixed implementation choices

| Area | Decision |
| --- | --- |
| Runtime | Python 3.12 managed by `uv` |
| API | FastAPI, Pydantic v2, generated OpenAPI |
| Domain | Framework-independent Python package |
| Persistence | PostgreSQL with Alembic; pgvector provisioned, retrieval deferred until measured |
| ORM | SQLAlchemy 2 typed mappings |
| Model integration | LangChain provider adapters behind an application-owned model gateway |
| Agent workflows | Bounded LangGraph workflows; never the global scheduler or canonical store |
| Observability | Durable PostgreSQL audit records plus optional LangSmith development/evaluation traces |
| Frontend | Vue 3, TypeScript, Vite; generated API types |
| Realtime | REST commands plus WebSocket event cursors when the UI needs server-pushed updates |
| Testing | Pytest, property/state-machine tests where useful, Vitest, Playwright, deterministic scenario harness |
| Initial deployment | One local application process plus PostgreSQL container |
| Later deployment | Replaceable model and image workers; Temporal only after promotion criteria |
| Rules | D&D-inspired fantasy simulation using 0-100 stats, stamina, mana, injuries, and conditions; no HP in the initial ruleset |
| Canon | One world, one active timeline, committed events plus transactional projections |

## 4. Document set

| Document | Purpose |
| --- | --- |
| [01_PRODUCT_CHARTER.md](01_PRODUCT_CHARTER.md) | Product promise, roles, modes, scope, non-goals, and success measures |
| [02_SYSTEM_ARCHITECTURE.md](02_SYSTEM_ARCHITECTURE.md) | Components, dependency direction, execution flow, concurrency, and source layout |
| [03_DOMAIN_AND_PERSISTENCE.md](03_DOMAIN_AND_PERSISTENCE.md) | Ubiquitous language, aggregates, state machines, commands, effects, events, schema, and invariants |
| [04_AI_CONTEXT_AND_TRACING.md](04_AI_CONTEXT_AND_TRACING.md) | LangChain/LangGraph boundaries, context assembly, model profiles, tracing, and structured outputs |
| [05_API_AND_FRONTEND.md](05_API_AND_FRONTEND.md) | API contracts, event streaming, Vue architecture, visual-novel UX, and accessibility |
| [06_CONTENT_RULES_AND_IMAGES.md](06_CONTENT_RULES_AND_IMAGES.md) | World content, RPG rules, narrative quality, pixel-art assets, and D&D boundary |
| [07_STAGED_ROADMAP.md](07_STAGED_ROADMAP.md) | Stage sequence, dependencies, promotion rules, and product proofs |
| [08_STAGE_0_EXECUTION.md](08_STAGE_0_EXECUTION.md) | Complete deterministic-foundation task packets and hard exit gate |
| [09_STAGE_1_EXECUTION.md](09_STAGE_1_EXECUTION.md) | First autonomous two-character vertical slice and task packets |
| [10_STAGES_2_TO_5_EXECUTION.md](10_STAGES_2_TO_5_EXECUTION.md) | Seven-day, month, local-model/image, and generational execution plans |
| [11_TESTING_AND_EVALUATION.md](11_TESTING_AND_EVALUATION.md) | Test strategy, fault matrix, LLM evaluations, datasets, and stage evidence |
| [12_OPERATIONS_SECURITY_AND_RECOVERY.md](12_OPERATIONS_SECURITY_AND_RECOVERY.md) | Configuration, secrets, backup, restore, health, security, and failure handling |
| [13_EXECUTION_CONTROL.md](13_EXECUTION_CONTROL.md) | Task lifecycle, dependency lanes, ownership, evidence, review, and status protocol |

## 5. Non-negotiable engineering rules

1. Canon lives in PostgreSQL, never in a model transcript, graph checkpoint, frontend store, generated image, or prose summary.
2. Every canonical mutation follows `Command -> Validation/Resolution -> Typed Effects -> Transaction -> Event and Projections`.
3. Remote model, embedding, image, and network calls never run inside a database transaction.
4. Models return proposals. Only deterministic application services validate and commit.
5. Structured effects commit before narration is generated or published as fact.
6. Every state-changing command and retryable task has an idempotency key.
7. Every affected aggregate uses an expected optimistic version.
8. One sealed phase snapshot feeds all same-phase primary character intents.
9. Perspective filters run before semantic retrieval or prompt assembly.
10. The domain imports no FastAPI, SQLAlchemy, LangChain, LangGraph, provider SDK, Vue, or infrastructure module.
11. LangGraph checkpoints resume bounded reasoning work only. They never represent world canon or character identity.
12. Generated prose and images are rebuildable presentation assets with source event and version references.
13. A stage may add only work required by its demonstration or hard exit gate.
14. Every persistent table and abstraction introduced in a stage must be exercised by that stage's proof.

## 6. Execution protocol

1. Work only from the active stage document.
2. Select a ready task whose dependencies are complete.
3. Restate its owned files, contracts, non-goals, and observable acceptance criteria.
4. Implement one complete vertical behavior where possible.
5. Run the narrow behavioral scenario named by the task.
6. Record evidence and any contract changes.
7. Complete the task only when its acceptance criteria and relevant cross-cutting checks pass.
8. Run the full stage gate only after all stage tasks are complete.
9. Freeze the stage's schema, prompt, seed, and API versions at promotion.
10. Do not start the next stage while a hard gate is failing or waived without an explicit decision record.

## 7. Definition of done

A task is done only when:

- the requested behavior exists end to end;
- canonical ownership and transaction rules are preserved;
- failure, retry, and duplicate behavior are defined;
- perspective and permission boundaries are enforced;
- focused verification passes;
- generated schemas or clients affected by the change are refreshed;
- no temporary script, mock, compatibility path, or obsolete writer remains unless the task explicitly owns it;
- documentation reflects any changed public contract.

A stage is done only when its hard exit gate and demonstration run from a clean environment and produce a retained evidence bundle.

## 8. Initial execution target

Start with [08_STAGE_0_EXECUTION.md](08_STAGE_0_EXECUTION.md). The first promoted artifact is deliberately not a game UI. It is a restart-safe deterministic world kernel that proves one command cannot create duplicate canon.