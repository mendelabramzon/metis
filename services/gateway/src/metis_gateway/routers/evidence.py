"""Evidence drill-down: expand a citation back through the truth hierarchy.

Read-only, member-gated views over a workspace's evidence — a claim -> its source spans (with the
quoted text) -> the raw artifact, plus the consolidated memory cell. Backs the evidence browser; an
entity not in the caller's workspace is a 404 (the same isolation boundary as every workspace read).
"""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, MemberDep
from metis_gateway.errors import NotFoundError
from metis_gateway.schemas import (
    ArtifactEvidenceView,
    ClaimEvidenceView,
    MemCellEvidenceView,
    SpanView,
)

router = APIRouter(prefix="/workspaces", tags=["evidence"])


@router.get("/{workspace_id}/claims/{claim_id}", response_model=ClaimEvidenceView)
async def claim_evidence(
    claim_id: str, context: MemberDep, backend: BackendDep
) -> ClaimEvidenceView:
    """A claim's text and the source spans that support it (each with its quoted evidence)."""
    evidence = await backend.workspace_for(context.workspace.id).claim_evidence(claim_id)
    if evidence is None:
        raise NotFoundError(f"no claim {claim_id!r} in this workspace")
    return ClaimEvidenceView(
        claim_id=evidence.claim_id,
        text=evidence.text,
        confidence=evidence.confidence,
        negated=evidence.negated,
        sensitivity=evidence.sensitivity,
        spans=[
            SpanView(
                source_span_id=span.source_span_id,
                artifact_id=span.artifact_id,
                doc_id=span.doc_id,
                char_start=span.char_start,
                char_end=span.char_end,
                page=span.page,
                quote=span.quote,
            )
            for span in evidence.spans
        ],
    )


@router.get("/{workspace_id}/artifacts/{artifact_id}", response_model=ArtifactEvidenceView)
async def artifact_evidence(
    artifact_id: str, context: MemberDep, backend: BackendDep
) -> ArtifactEvidenceView:
    """The source artifact a span points back to (filename, type, connector, when ingested)."""
    evidence = await backend.workspace_for(context.workspace.id).artifact_evidence(artifact_id)
    if evidence is None:
        raise NotFoundError(f"no artifact {artifact_id!r} in this workspace")
    return ArtifactEvidenceView(
        artifact_id=evidence.artifact_id,
        filename=evidence.filename,
        media_type=evidence.media_type,
        byte_size=evidence.byte_size,
        kind=evidence.kind,
        connector=evidence.connector,
        source_id=evidence.source_id,
        created_at=evidence.created_at,
        tombstoned=evidence.tombstoned,
    )


@router.get("/{workspace_id}/memory/{mem_cell_id}", response_model=MemCellEvidenceView)
async def mem_cell_evidence(
    mem_cell_id: str, context: MemberDep, backend: BackendDep
) -> MemCellEvidenceView:
    """A consolidated memory cell and the claim ids it rests on (drill into each via /claims)."""
    evidence = await backend.workspace_for(context.workspace.id).mem_cell_evidence(mem_cell_id)
    if evidence is None:
        raise NotFoundError(f"no memory cell {mem_cell_id!r} in this workspace")
    return MemCellEvidenceView(
        mem_cell_id=evidence.mem_cell_id,
        summary=evidence.summary,
        sensitivity=evidence.sensitivity,
        claim_ids=list(evidence.claim_ids),
    )
