"""Execution dispatch: run a proposed action against the real engines, risk-gated.

The second half of the "human agency over side effects" invariant. Interpreting a command into a
typed :class:`ProposedAction` is one step; *executing* it is a separate, gated one:

- ``READ_ONLY`` actions (answer / find-evidence / draft / inspect-source) run immediately.
- Effectful actions (``REVERSIBLE`` and the write tiers) execute only once they are ``APPROVED``.
- ``EXTERNAL`` side effects stay out of Stage 1.

Writes that would touch memory or the wiki must flow through the claim pipeline / review inboxes,
not a direct write (the truth-hierarchy invariant), so ``CREATE_MEMORY`` / ``CREATE_WIKI_PATCH`` /
``PROPOSE_SOURCE_CHANGE`` are deferred here rather than shortcut. Every execution emits an
``action.executed`` audit event, so a run is always on the record with its actor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from metis_core.wiki.approval import WikiPatchReview
from metis_gateway.backend import Backend
from metis_gateway.errors import ConflictError, NotFoundError, TooManyRequestsError
from metis_gateway.models import over_daily_cap
from metis_ingestion import ConnectorScheduler
from metis_protocol import (
    ActionKind,
    ActionRisk,
    ActionStatus,
    AgentKind,
    Attribution,
    AuditEvent,
    AuditId,
    PolicyState,
    ProposedAction,
    Provenance,
    Sensitivity,
    SourceId,
    WikiOp,
    WikiPatch,
    WikiPatchId,
    is_at_least,
    new_id,
)
from metis_runtime.agent import AgentRequest

# Read-only kinds answered by running the query engine over the workspace's evidence.
_QUERY_KINDS = {ActionKind.ANSWER, ActionKind.FIND_EVIDENCE, ActionKind.DRAFT_RESPONSE}


@dataclass
class ExecutionOutcome:
    """What an execution produced — projected onto the wire by the router."""

    detail: str  # human-readable "what happened" (always set)
    answer: str | None = None
    sufficient: bool | None = None
    # (claim_id, source_span_id, artifact_id) rows, mirroring the query router's flat citations.
    citations: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    job_id: str | None = None  # for START_SYNC: the queued connector-sync job
    doc_id: str | None = None  # for CREATE_MEMORY: the doc the assertion was ingested as
    patch_id: str | None = None  # for CREATE_WIKI_PATCH: the patch queued for review


def guard_executable(action: ProposedAction) -> None:
    """Reject an action the risk tier forbids running (ConflictError, status left unchanged).

    Read-only actions run from ``PROPOSED``; effectful ones require ``APPROVED``; ``EXTERNAL`` is
    blocked; an already ``EXECUTED``/``REJECTED`` action is not re-run."""
    if action.status in (ActionStatus.EXECUTED, ActionStatus.REJECTED):
        raise ConflictError(f"action is already {action.status.value}")
    if action.risk is ActionRisk.EXTERNAL:
        raise ConflictError("external side effects are out of scope for Stage 1")
    if action.risk is not ActionRisk.READ_ONLY and action.status is not ActionStatus.APPROVED:
        raise ConflictError(f"{action.risk.value} actions must be approved before execution")


async def execute_action(
    action: ProposedAction, *, backend: Backend, actor: str, max_sensitivity: Sensitivity
) -> ExecutionOutcome:
    """Dispatch a (guarded) action to its engine and audit it. Call :func:`guard_executable` first.

    Parameter/lookup problems raise ConflictError/NotFoundError (a bad request, status unchanged); a
    genuine engine failure propagates so the caller can record the action ``FAILED``."""
    if action.kind in _QUERY_KINDS:
        outcome = await _run_query(action, backend=backend, max_sensitivity=max_sensitivity)
    elif action.kind is ActionKind.INSPECT_SOURCE:
        outcome = await _inspect_source(action, backend=backend)
    elif action.kind is ActionKind.START_SYNC:
        outcome = await _start_sync(action, backend=backend)
    elif action.kind is ActionKind.CREATE_MEMORY:
        outcome = await _create_memory(action, backend=backend)
    elif action.kind is ActionKind.CREATE_WIKI_PATCH:
        outcome = await _create_wiki_patch(action, backend=backend, actor=actor)
    else:  # PROPOSE_SOURCE_CHANGE — a connector/source change is itself an approval, deferred
        raise ConflictError(f"execution for {action.kind.value} actions is not implemented yet")
    await _audit(action, backend=backend, actor=actor, detail=outcome.detail)
    return outcome


def _first_str(action: ProposedAction, keys: tuple[str, ...]) -> str | None:
    """The first non-empty string among the named parameters (interpreter params are free-form)."""
    for key in keys:
        value = action.parameters.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


async def _run_query(
    action: ProposedAction, *, backend: Backend, max_sensitivity: Sensitivity
) -> ExecutionOutcome:
    """Run the agent loop on the action's workspace under its model policy + spend cap."""
    ws_id = action.workspace_id
    query_text = str(action.parameters.get("query") or action.command)
    policy = await backend.identity.get_model_policy(ws_id)
    if backend.spend is not None and over_daily_cap(policy, backend.spend.today_total(ws_id)):
        raise TooManyRequestsError("workspace daily model-spend cap reached")
    allow_external = policy.allow_external_models
    run = await backend.agent_for(ws_id, allow_external=allow_external).run(
        AgentRequest(
            workspace_id=ws_id,
            instruction=query_text,
            max_sensitivity=max_sensitivity,
            top_k=None,
        )
    )
    answer = run.answer
    citations: list[tuple[str, str | None, str | None]] = []
    if answer is not None:
        workspace = backend.workspace_for(ws_id, allow_external=allow_external)
        citations = list(await workspace.citation_rows(answer.claims))
    return ExecutionOutcome(
        detail=f"ran {action.kind.value}",
        answer=answer.text if answer is not None else run.summary,
        sufficient=answer.sufficient if answer is not None else False,
        citations=citations,
    )


async def _inspect_source(action: ProposedAction, *, backend: Backend) -> ExecutionOutcome:
    """Read-only: a named source's config + recent runs, or the source list if none is named."""
    raw_id = action.parameters.get("source_id")
    if not raw_id:
        sources = await backend.sources.list_all()
        listing = ", ".join(f"{s.name} ({s.connector})" for s in sources) or "none configured"
        return ExecutionOutcome(detail=f"sources: {listing}")
    source = await backend.sources.get(SourceId(str(raw_id)))
    if source is None:
        raise NotFoundError(f"no source {raw_id!r}")
    runs = await backend.sources.runs_for(source.id, limit=5)
    cursor = await backend.sources.get_cursor(source.id)
    return ExecutionOutcome(
        detail=(
            f"{source.name} ({source.connector}, {source.sensitivity.value}); "
            f"{len(runs)} recent run(s); cursor {'set' if cursor is not None else 'none'}"
        )
    )


async def _start_sync(action: ProposedAction, *, backend: Backend) -> ExecutionOutcome:
    """Enqueue a connector-sync job for the named source (the POST /sources/{id}/sync path)."""
    raw_id = action.parameters.get("source_id")
    if not raw_id:
        raise ConflictError("start_sync requires a 'source_id' parameter")
    source = await backend.sources.get(SourceId(str(raw_id)))
    if source is None:
        raise NotFoundError(f"no source {raw_id!r}")
    cursor = await backend.sources.get_cursor(source.id)
    job_id = await ConnectorScheduler(backend.jobs).schedule_poll(
        workspace_id=source.workspace_id,
        connector=source.connector,
        source_id=source.id,
        cursor=cursor.cursor if cursor is not None else None,
    )
    return ExecutionOutcome(detail=f"queued sync job for {source.name}", job_id=str(job_id))


async def _create_memory(action: ProposedAction, *, backend: Backend) -> ExecutionOutcome:
    """Remember an assertion by *ingesting it through the claim pipeline* (truth hierarchy): it
    becomes a user-sourced doc → claims → mem cell with provenance, never a direct memory write."""
    content = _first_str(action, ("content", "text", "note", "memory", "summary"))
    if content is None:
        raise ConflictError("create_memory requires a 'content' (or text/note) parameter")
    ws_id = action.workspace_id
    policy = await backend.identity.get_model_policy(ws_id)
    workspace = backend.workspace_for(ws_id, allow_external=policy.allow_external_models)
    outcome = await workspace.ingest_bytes(
        filename=f"memory-{action.id}.md",
        data=content.encode("utf-8"),
        sensitivity=action.sensitivity,
        connector="command",
    )
    return ExecutionOutcome(
        detail=f"ingested via the pipeline as doc {outcome.doc_id} ({outcome.claims} claim(s))",
        doc_id=outcome.doc_id,
    )


async def _create_wiki_patch(
    action: ProposedAction, *, backend: Backend, actor: str
) -> ExecutionOutcome:
    """Propose a wiki patch into the review inbox (never a direct write): a new page from the
    command, held PROPOSED for the existing wiki approval to commit (or reject)."""
    body = _first_str(action, ("body", "content", "markdown", "text")) or action.command
    title = _first_str(action, ("title", "topic", "page")) or action.summary or "Untitled"
    sensitivity = action.sensitivity
    patch = WikiPatch(
        id=new_id(WikiPatchId),
        provenance=Provenance(
            workspace_id=action.workspace_id,
            attribution=Attribution(agent_kind=AgentKind.HUMAN, agent=actor),
        ),
        policy=PolicyState(
            sensitivity=sensitivity,
            allow_external_models=not is_at_least(sensitivity, Sensitivity.RESTRICTED),
        ),
        created_at=datetime.now(UTC),
        op=WikiOp.CREATE,
        title=title,
        body_markdown=body,
        rationale=f"proposed from command: {action.command}",
    )
    await backend.wiki.propose(WikiPatchReview(patch=patch))
    return ExecutionOutcome(
        detail=f"proposed wiki patch {patch.id} for review (not yet committed)",
        patch_id=str(patch.id),
    )


async def _audit(action: ProposedAction, *, backend: Backend, actor: str, detail: str) -> None:
    await backend.audit.emit(
        AuditEvent(
            id=new_id(AuditId),
            workspace_id=action.workspace_id,
            occurred_at=datetime.now(UTC),
            actor=Attribution(agent_kind=AgentKind.HUMAN, agent=actor),
            action="action.executed",
            target_id=str(action.id),
            target_kind=action.kind.value,
            payload={"detail": detail},
        )
    )
