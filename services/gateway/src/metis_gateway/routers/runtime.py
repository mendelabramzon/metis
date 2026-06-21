"""Background runtime jobs: enqueue research; the result lands in the wiki review inbox.

Unlike the inline ``/query``, this offloads the work to the runtime worker over the durable queue:
the worker answers from the workspace's memory and files a grounded answer back as a wiki-patch
proposal (for review, never a direct write). Workspace-scoped + membership-gated like the other
per-workspace surfaces; the returned job id is for tracking, and the result shows up under
``GET /wiki/patches`` once processed.
"""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, WorkspaceWriterDep
from metis_gateway.schemas import ResearchRequest, RuntimeJobView
from metis_runtime import build_research_job

router = APIRouter(prefix="/workspaces", tags=["runtime"])


@router.post("/{workspace_id}/runtime/research", response_model=RuntimeJobView, status_code=202)
async def research(
    body: ResearchRequest, context: WorkspaceWriterDep, backend: BackendDep
) -> RuntimeJobView:
    """Queue a background research job; the runtime worker files a grounded proposal back."""
    job = build_research_job(workspace_id=context.workspace.id, query=body.query)
    await backend.jobs.enqueue(job)
    return RuntimeJobView(job_id=str(job.id), kind=job.kind)
