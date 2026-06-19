"""Contradiction inbox: conflicting evidence surfaced for review, never silently merged.

The maintainer detects contradictions between claims and persists them; this is the review surface.
List the open ones (member-gated), then resolve or dismiss each (writer-gated). The claim ids drill
into the evidence browser. A contradiction not in the caller's workspace is a 404.
"""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, MemberDep, WorkspaceWriterDep
from metis_gateway.errors import NotFoundError
from metis_gateway.schemas import ContradictionUpdate, ContradictionView
from metis_protocol import Contradiction, ContradictionStatus

router = APIRouter(prefix="/workspaces", tags=["contradictions"])


def _view(contradiction: Contradiction) -> ContradictionView:
    return ContradictionView(
        contradiction_id=str(contradiction.id),
        summary=contradiction.summary,
        explanation=contradiction.explanation,
        status=contradiction.status,
        claim_ids=[str(ref.claim_id) for ref in contradiction.claims],
        sensitivity=contradiction.policy.sensitivity,
        created_at=contradiction.created_at,
    )


@router.get("/{workspace_id}/contradictions", response_model=list[ContradictionView])
async def list_contradictions(
    context: MemberDep,
    backend: BackendDep,
    status: ContradictionStatus = ContradictionStatus.OPEN,
) -> list[ContradictionView]:
    """The workspace's contradictions at a given status — the inbox (defaults to the open ones)."""
    found = await backend.workspace_for(context.workspace.id).list_contradictions(status=status)
    return [_view(contradiction) for contradiction in found]


@router.patch("/{workspace_id}/contradictions/{contradiction_id}", response_model=ContradictionView)
async def review_contradiction(
    contradiction_id: str,
    body: ContradictionUpdate,
    context: WorkspaceWriterDep,
    backend: BackendDep,
) -> ContradictionView:
    """Resolve or dismiss a contradiction (writer-gated). 404 if it is not in this workspace."""
    updated = await backend.workspace_for(context.workspace.id).resolve_contradiction(
        contradiction_id, status=body.status
    )
    if updated is None:
        raise NotFoundError(f"no contradiction {contradiction_id!r} in this workspace")
    return _view(updated)
