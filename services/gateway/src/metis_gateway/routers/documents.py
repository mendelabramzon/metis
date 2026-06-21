"""Uploaded documents: list and erase a workspace's directly-uploaded files.

Uploads register no ``SourceConfig``, so they never appear under ``/sources`` and the
source-erasure path can't reach them — this is their list + delete surface. Both are workspace
*writer* gated (uploading is a writer action, so managing one's uploads is too) and scoped to the
``upload`` connector: a connector-synced artifact is not touched here (it is erased through its
source, operator-gated, or via the admin artifact-erasure path).
"""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, MemberDep, WorkspaceWriterDep
from metis_gateway.errors import NotFoundError
from metis_gateway.schemas import ArtifactEvidenceView, ErasureView

router = APIRouter(prefix="/workspaces/{workspace_id}/documents", tags=["documents"])


@router.get("", response_model=list[ArtifactEvidenceView])
async def list_documents(context: MemberDep, backend: BackendDep) -> list[ArtifactEvidenceView]:
    """The workspace's uploaded documents, newest first — what a member can see and erase."""
    docs = await backend.workspace_for(context.workspace.id).list_documents()
    return [
        ArtifactEvidenceView(
            artifact_id=d.artifact_id,
            filename=d.filename,
            media_type=d.media_type,
            byte_size=d.byte_size,
            kind=d.kind,
            connector=d.connector,
            source_id=d.source_id,
            created_at=d.created_at,
            tombstoned=d.tombstoned,
        )
        for d in docs
    ]


@router.delete("/{artifact_id}", response_model=ErasureView)
async def delete_document(
    artifact_id: str, context: WorkspaceWriterDep, backend: BackendDep
) -> ErasureView:
    """Erase an uploaded document: tombstone its derived graph and delete its raw blob.

    Resolved against the workspace's own engine (an unknown id is a 404, never a cross-workspace
    delete) and scoped to uploads — a connector-synced artifact is not deletable here (it is erased
    through its source). Writer-gated, mirroring upload.
    """
    workspace = backend.workspace_for(context.workspace.id)
    evidence = await workspace.artifact_evidence(artifact_id)
    if evidence is None or evidence.connector != "upload" or evidence.tombstoned:
        raise NotFoundError(f"no uploaded document {artifact_id!r} in this workspace")
    result = await workspace.erase_artifact(artifact_id)
    if result is None:  # raced with another delete between the lookup and the erase
        raise NotFoundError(f"no uploaded document {artifact_id!r} in this workspace")
    tombstoned = result.tombstoned
    return ErasureView(
        artifact_tombstoned=tombstoned.raw_artifacts > 0,
        normalized_docs=tombstoned.normalized_docs,
        parsed_docs=tombstoned.parsed_docs,
        segments=tombstoned.segments,
        claims=tombstoned.claims,
        mem_cells=tombstoned.mem_cells,
        blobs_erased=result.blobs_erased,
    )
