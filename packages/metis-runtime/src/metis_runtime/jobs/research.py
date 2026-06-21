"""The ``runtime.research`` job: answer a question in the background and file the answer back.

The runtime's compounding move as an async job: run the Stage-8 query engine over the workspace's
memory and, when the answer is sufficient and grounded, propose filing it back as a wiki patch (the
same trust boundary as everywhere — a *proposal* in the review inbox, never a direct write). The
proposal surfaces through the wiki review inbox (``GET /wiki/patches``), so the job needs no
return-to-caller channel. Insufficient evidence files nothing.

:func:`build_research_job` is the producer helper (the gateway enqueues it); :class:`ResearchJob` is
the handler the worker dispatches to.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from metis_core.wiki.approval import WikiPatchReview
from metis_protocol import (
    AgentKind,
    Attribution,
    Job,
    JobId,
    PolicyState,
    Provenance,
    QueryId,
    QueryRequest,
    Sensitivity,
    WikiOp,
    WikiPatch,
    WikiPatchId,
    WorkspaceId,
    is_at_least,
    new_id,
)
from metis_runtime.jobs.base import RuntimeDeps, RuntimeJobOutcome, workspace_of
from metis_runtime.query import propose_fileback

RESEARCH_JOB_KIND = "runtime.research"


def build_research_job(
    *, workspace_id: WorkspaceId, query: str, max_sensitivity: Sensitivity = Sensitivity.INTERNAL
) -> Job:
    """A ``runtime.research`` job for the durable queue (the gateway enqueues this)."""
    return Job(
        id=new_id(JobId),
        workspace_id=workspace_id,
        kind=RESEARCH_JOB_KIND,
        payload={
            "workspace_id": str(workspace_id),
            "query": query,
            "max_sensitivity": max_sensitivity.value,
        },
        created_at=datetime.now(UTC),
    )


def _sensitivity(payload: Mapping[str, Any]) -> Sensitivity:
    raw = payload.get("max_sensitivity")
    try:
        return Sensitivity(str(raw)) if raw is not None else Sensitivity.INTERNAL
    except ValueError:
        return Sensitivity.INTERNAL


class ResearchJob:
    """Answer the payload's query and file a grounded answer back as a wiki-patch proposal."""

    kind = RESEARCH_JOB_KIND

    async def run(self, deps: RuntimeDeps, payload: Mapping[str, Any]) -> RuntimeJobOutcome:
        workspace_id = workspace_of(payload)
        text = str(payload.get("query") or payload.get("text") or "").strip()
        if not text:
            return RuntimeJobOutcome(
                kind=self.kind, summary="no query in payload", counts={"filed": 0}
            )

        query = QueryRequest(
            id=new_id(QueryId),
            workspace_id=workspace_id,
            text=text,
            max_sensitivity=_sensitivity(payload),
        )
        answer = await deps.query_engine.answer(query)
        # File back only a sufficient, grounded answer — a proposal, never a direct write.
        if propose_fileback(query, answer, kind="wiki") is None:
            return RuntimeJobOutcome(
                kind=self.kind, summary="insufficient evidence; nothing filed", counts={"filed": 0}
            )

        patch = WikiPatch(
            id=new_id(WikiPatchId),
            provenance=Provenance(
                workspace_id=workspace_id,
                attribution=Attribution(agent_kind=AgentKind.SYSTEM, agent="runtime-worker"),
            ),
            policy=PolicyState(
                sensitivity=answer.sensitivity,
                allow_external_models=not is_at_least(answer.sensitivity, Sensitivity.RESTRICTED),
            ),
            created_at=datetime.now(UTC),
            op=WikiOp.CREATE,
            title=text[:80],
            body_markdown=answer.text,
            rationale=f"runtime research: {text}",
        )
        await deps.wiki_inbox(workspace_id).propose(WikiPatchReview(patch=patch))
        return RuntimeJobOutcome(
            kind=self.kind,
            summary=f"filed wiki proposal {patch.id} for review",
            counts={"filed": 1},
        )
