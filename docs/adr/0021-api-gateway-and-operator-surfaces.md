# ADR 0021: API/UI/ops gateway — a thin HTTP layer, scoped auth, and one approval inbox

- Status: Accepted
- Date: 2026-06-19
- Deciders: Metis maintainers

## Context

Stage 12 exposes the engine to users and operators: a FastAPI gateway over source management,
ingestion, query/chat, wiki, skills, the approval inbox, jobs/ops, and audit, plus a minimal debug
UI. The plan is emphatic that the gateway is *thin* — it calls the existing packages and maps to
HTTP, holding no business logic — and that approvals are explicit/auditable and failed jobs
inspectable/retryable. The open question is how to keep the surface fully testable without standing
up Postgres/MinIO/model providers for every request.

## Decision

**The gateway is a thin HTTP projection over a swappable backend container.** Routers map a request
to a backend call and a protocol object to a wire DTO — nothing more. All dependencies live on a
``Backend`` dataclass wired once at app assembly and reached through FastAPI ``Depends``; swapping
the in-memory wiring for durable stores (Stage 15) means replacing the container, not touching a
router.

**The backend wires the *real* engine components over in-memory stores.** It composes the real
Stage 10 ``AgentLoop`` and Stage 9 ``SkillRunner``, and a workspace that ingests with the real Stage
3 ``BaselineExtractor`` — so claims and citations are genuine, not stubbed — backed by in-memory
document/claim/job/audit stores and the in-process ``ApprovalQueue``. This runs the whole API,
including a real ingest→extract→query→cited-answer loop, with no external infra; the Postgres/MinIO
swap is a deployment concern. (This mirrors the codebase's "in-process now, durable later" pattern:
the approval queue and task store are already in-process.)

**Auth is two ordered scopes enforced at the boundary, and the scope caps sensitivity.** A bearer
token resolves to a ``Principal`` with a scope (``user`` < ``operator``) and a sensitivity ceiling
(user→``INTERNAL``, operator→``RESTRICTED``). Query/read needs ``user``; approvals, jobs, and audit
need ``operator``. The ceiling is passed into the query so an answer can only rest on evidence the
caller may see — sensitivity is enforced before retrieval, not filtered after. Token-to-scope is a
dev stand-in; encrypted credentials and SSO are Stage 14, but the per-request ``Principal`` seam is
in place.

**One inbox unifies action and wiki-patch approvals, and approving is always audited.** The
``ApprovalInbox`` merges the Stage 9/10 skill-action queue and the Stage 7 wiki-patch reviews into a
single list keyed by ``(kind, id)``; approving dispatches to the right state machine and emits an
``approval.granted`` audit event attributed to the operator. A reviewer has one queue, and every
human decision is on the record.

**Jobs expose an inspect/retry surface; there is no enqueue endpoint.** Jobs originate inside the
engine (ingestion/connectors), so the ops API only lists, inspects, and retries — a failed job moves
back to ``PENDING`` with an incremented attempt count. Errors are surfaced per job for debugging.

**Consistent errors and a minimal debug UI.** Routers raise a typed ``ApiError`` rendered as
``{"error": {code, message}}``; a single self-contained ``index.html`` (chat-with-citations,
sources, approvals inbox, jobs, audit) is the operator's window into engine state — a debug surface,
not a product.

## Consequences

- The four acceptance checks hold with no Docker: an API flow ingests a fixture and returns a cited
  answer; approving an action is explicit and lands in the audit log; a failed job is inspectable and
  retryable; and query responses carry claim/source-span citations (and stay honest when evidence is
  insufficient). The FastAPI ``TestClient`` drives the whole surface in-process.
- New deps on the gateway service: ``fastapi`` plus the workspace packages it orchestrates
  (``metis-protocol``/``core``/``ingestion``/``runtime``). Import-linter does not constrain services,
  so this is allowed; the gateway depends inward on the packages, never the reverse.
- ``run()`` now assembles the real app (the Stage 0 ``--dry-run`` boot contract is preserved); binding
  it to an ASGI server is Stage 15. Streaming chat, per-workspace multi-tenancy, and rate limiting
  are deferred but seam-compatible.

## Alternatives considered

- **A Postgres/MinIO-backed gateway for all tests**: faithful but couples every API test to Docker
  and reruns engine internals already covered in Stages 3–11; the in-memory backend keeps the suite
  about the *surface* while still exercising real extraction/agent/skill components.
- **Business logic in routers**: explicitly rejected by the plan and ``package-decomposition.md``;
  routers stay a projection so the canonical logic has exactly one home.
- **Separate approval inboxes for actions vs wiki patches**: rejected — reviewers need one queue;
  unifying them at the API is the point of the inbox.
- **A job enqueue endpoint**: rejected — jobs are produced by the engine, not clients; exposing
  enqueue would invite the gateway to grow orchestration logic it should not own.
- **A SPA/build-tooled UI**: out of scope; a single static HTML console is enough to debug ingestion
  and retrieval, with no build step or churn.
