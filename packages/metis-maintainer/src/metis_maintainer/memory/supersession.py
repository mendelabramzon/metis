"""Append-only memory revision: build create / supersede / retract patches.

Memory is never edited in place. A :class:`~metis_protocol.MemoryPatch` records the intent
(``create`` a new cell, ``supersede`` an old one with a newer cell, or ``retract`` a cell);
the store applies it by flipping a flag on the target row, which stays auditable. The
superseding cell also carries a ``supersedes`` ref back to the cell it replaces, so the
chain is walkable in both directions (:func:`mark_supersedes`).
"""

from __future__ import annotations

from metis_maintainer.memory._build import maintainer_provenance, now_utc
from metis_protocol import (
    MemCell,
    MemCellId,
    MemCellRef,
    MemoryOp,
    MemoryPatch,
    MemoryPatchId,
    PolicyState,
    WorkspaceId,
    new_id,
)


def _patch(
    *,
    workspace_id: WorkspaceId,
    policy: PolicyState,
    op: MemoryOp,
    target_id: str,
    supersedes_id: str | None = None,
    reason: str,
) -> MemoryPatch:
    inputs = [target_id, *([supersedes_id] if supersedes_id is not None else [])]
    return MemoryPatch(
        id=new_id(MemoryPatchId),  # fresh id: the patch log is append-only, re-runs append
        provenance=maintainer_provenance(
            workspace_id,
            agent="supersession",
            operation=f"memory_patch.{op.value}",
            inputs=inputs,
        ),
        policy=policy,
        created_at=now_utc(),
        op=op,
        target_id=target_id,
        supersedes_id=supersedes_id,
        reason=reason,
    )


def create_patch(cell: MemCell, *, reason: str = "consolidated from extraction") -> MemoryPatch:
    """Record that ``cell`` was created (the append-only log entry for a new memory)."""
    return _patch(
        workspace_id=cell.provenance.workspace_id,
        policy=cell.policy,
        op=MemoryOp.CREATE,
        target_id=str(cell.id),
        reason=reason,
    )


def mark_supersedes(new_cell: MemCell, superseded_id: MemCellId) -> MemCell:
    """Stamp ``new_cell`` with a back-ref to the cell it replaces."""
    return new_cell.model_copy(update={"supersedes": MemCellRef(mem_cell_id=superseded_id)})


def supersede_patch(*, superseded_id: MemCellId, by_cell: MemCell, reason: str = "") -> MemoryPatch:
    """A patch retiring ``superseded_id`` in favour of ``by_cell`` (target is the old cell)."""
    return _patch(
        workspace_id=by_cell.provenance.workspace_id,
        policy=by_cell.policy,
        op=MemoryOp.SUPERSEDE,
        target_id=str(superseded_id),
        supersedes_id=str(by_cell.id),
        reason=reason,
    )


def retract_patch(*, cell: MemCell, reason: str) -> MemoryPatch:
    """A patch withdrawing ``cell`` (it stays stored and auditable, but hidden from queries)."""
    return _patch(
        workspace_id=cell.provenance.workspace_id,
        policy=cell.policy,
        op=MemoryOp.RETRACT,
        target_id=str(cell.id),
        reason=reason,
    )
