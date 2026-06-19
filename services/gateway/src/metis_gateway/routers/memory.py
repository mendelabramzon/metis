"""Memory review: the write/manage/read loop over consolidated memory.

Review the workspace's active memory cells (member-gated), then retract one (remove it from memory)
or supersede it (mark it stale) — each an append-only memory patch, attributed to the reviewer
(writer-gated). Accepting a cell is just leaving it active. A cell not in this workspace is a 404.
"""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, MemberDep, WorkspaceWriterDep
from metis_gateway.errors import NotFoundError
from metis_gateway.schemas import MemoryCellView, MemoryRevisionRequest, MemoryRevisionResult
from metis_protocol import MemCell, MemoryOp

router = APIRouter(prefix="/workspaces", tags=["memory"])


def _cell_view(cell: MemCell) -> MemoryCellView:
    return MemoryCellView(
        mem_cell_id=str(cell.id),
        summary=cell.summary,
        sensitivity=cell.policy.sensitivity,
        claim_ids=[str(ref.claim_id) for ref in cell.claims],
        created_at=cell.created_at,
    )


@router.get("/{workspace_id}/memory", response_model=list[MemoryCellView])
async def list_memory(context: MemberDep, backend: BackendDep) -> list[MemoryCellView]:
    """The workspace's active memory cells — the review queue."""
    cells = await backend.workspace_for(context.workspace.id).list_memory()
    return [_cell_view(cell) for cell in cells]


async def _revise(
    *,
    backend: BackendDep,
    context: WorkspaceWriterDep,
    mem_cell_id: str,
    op: MemoryOp,
    reason: str,
) -> MemoryRevisionResult:
    cell = await backend.workspace_for(context.workspace.id).revise_mem_cell(
        mem_cell_id, op=op, reason=reason, actor=str(context.user.id)
    )
    if cell is None:
        raise NotFoundError(f"no memory cell {mem_cell_id!r} in this workspace")
    return MemoryRevisionResult(mem_cell_id=str(cell.id), op=op, summary=cell.summary)


@router.post("/{workspace_id}/memory/{mem_cell_id}/retract", response_model=MemoryRevisionResult)
async def retract_mem_cell(
    mem_cell_id: str,
    body: MemoryRevisionRequest,
    context: WorkspaceWriterDep,
    backend: BackendDep,
) -> MemoryRevisionResult:
    """Retract a memory cell — remove it from active memory (kept in the table for audit)."""
    return await _revise(
        backend=backend,
        context=context,
        mem_cell_id=mem_cell_id,
        op=MemoryOp.RETRACT,
        reason=body.reason,
    )


@router.post("/{workspace_id}/memory/{mem_cell_id}/supersede", response_model=MemoryRevisionResult)
async def supersede_mem_cell(
    mem_cell_id: str,
    body: MemoryRevisionRequest,
    context: WorkspaceWriterDep,
    backend: BackendDep,
) -> MemoryRevisionResult:
    """Supersede a memory cell — mark it stale/outdated (kept in the table for audit)."""
    return await _revise(
        backend=backend,
        context=context,
        mem_cell_id=mem_cell_id,
        op=MemoryOp.SUPERSEDE,
        reason=body.reason,
    )
