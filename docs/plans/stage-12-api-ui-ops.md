# Stage 12 Detailed Plan: API, UI, And Ops Surfaces

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 12. Builds on Stages 0–11.

This stage exposes the engine to users and operators: a FastAPI gateway covering source management, ingestion, query/chat, wiki browsing/patching, skill registry/run, the approval inbox, jobs/ops, and audit; plus a minimal web UI that surfaces enough state to debug ingestion and retrieval. Approvals are explicit and auditable; failed jobs can be retried or inspected.

## Objective

- Implement the FastAPI gateway with source, ingestion, query/chat, wiki, skill, approval, jobs/ops, and audit APIs.
- Implement a minimal web UI: chat with citations, wiki browser, source setup, job dashboard, approval inbox, skill run history, audit/event view.
- Ensure API flows cover the main engine loop and expose enough state to debug.

Non-goals: business logic (the gateway calls into the existing packages), deployment/ops infra (Stage 15).

## Package Ownership

- Owns: `services/gateway` (FastAPI) and a minimal web UI.
- The gateway is a thin orchestration/HTTP layer over `metis-core`, `metis-ingestion`, `metis-maintainer`, and `metis-runtime` — it holds no canonical business logic.
- Uses the entrypoint + settings conventions from Stage 0.

## Concrete Files And Modules To Create

```text
services/gateway/src/metis_gateway/
  app.py                 # FastAPI app assembly + dependency wiring
  routers/
    sources.py           # source management (register/configure connectors)
    ingestion.py         # trigger/monitor ingestion
    query.py             # query/chat with citations (streams answers)
    wiki.py              # wiki browse + patch review/approve
    skills.py            # skill registry + run
    approvals.py         # approval inbox (actions + patches)
    jobs.py              # jobs/ops: inspect/retry failed jobs
    audit.py             # audit/event view
  auth.py                # API auth (operator/user)
  schemas.py             # request/response models (reuse protocol where possible)
  errors.py              # error handling -> consistent API errors
  web/                   # minimal UI (chat, wiki browser, dashboards, inbox)

services/gateway/tests/
  test_engine_loop_e2e.py
  test_approvals_auditable.py
  test_job_retry.py
  test_query_citations.py
```

## Schemas And Interfaces Touched

- Reuses `metis-protocol` schemas at the API boundary where possible (`QueryRequest`, `SkillManifest`, `WikiPatch`, `AuditEvent`, job/source records).
- Calls into core stores, the ingestion pipeline, the maintainer, and the runtime agent; does not bypass their contracts.
- Surfaces the approval queue (Stages 9/10) and wiki approval (Stage 7) through one inbox.

## Implementation Steps

1. Assemble the FastAPI app and dependency wiring per the Stage 0 entrypoint convention.
2. Implement routers: sources, ingestion, query/chat (streaming answers with citations), wiki browse/patch, skills, approvals, jobs/ops, audit.
3. Implement API auth distinguishing operator vs user scopes; enforce sensitivity at the API boundary.
4. Build the minimal web UI: chat-with-citations, wiki browser, source setup, job dashboard, approval inbox, skill run history, audit/event view.
5. Wire failed-job inspection/retry through the jobs API; ensure approvals are explicit and auditable.
6. Add an end-to-end test exercising the main engine loop (ingest → query → answer with citations).

## Tests And Fixtures

- **Engine loop e2e** (`test_engine_loop_e2e.py`): API flow ingests a fixture, queries it, and returns a cited answer.
- **Approvals auditable** (`test_approvals_auditable.py`): approving an action/patch is explicit and recorded in the audit log.
- **Job retry** (`test_job_retry.py`): a failed job can be inspected and retried via the API.
- **Query citations** (`test_query_citations.py`): query responses include citations to source-backed evidence.

Fixtures: a small workspace loaded via the API, a pending approval, and a deliberately failed job.

## Acceptance Criteria

Traces to the Stage 12 "Validation" list:

- API flows cover the main engine loop.
- The UI exposes enough state to debug ingestion and retrieval.
- Approvals are explicit and auditable.
- Failed jobs can be retried or inspected.

## Risks And Open Questions

- **Thin gateway discipline**: resist putting business logic in routers; the gateway calls package APIs and maps to HTTP, nothing more (an explicit boundary in `package-decomposition.md`).
- **Streaming answers**: chat-with-citations benefits from streaming; design the query router to stream tokens and attach citations without buffering the whole answer.
- **AuthN/Z scope**: operator vs user scopes and per-workspace isolation must be enforced at the boundary; defer richer SSO to later but don't leave it open.
- **UI scope creep**: keep the UI minimal and debug-focused; it is a window into engine state, not a product surface yet.
- **Approval inbox unification**: actions (Stage 10) and wiki patches (Stage 7) should share one inbox model so reviewers have a single queue.
- **Backpressure/limits**: ingestion-trigger and skill-run endpoints need rate limiting to avoid overwhelming workers.
