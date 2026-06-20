"""File upload: ingest one or more documents into a workspace, with a per-file parse status.

A workspace writer uploads files (PDF/DOCX/XLSX/CSV/TXT/MD/HTML/EML) directly; each is run through
the real parser + extractor and reported individually, so one unsupported or malformed file in a
batch surfaces as a failed status rather than failing the whole request. Uploads land in the
caller's workspace (the membership gate), tagged with the ``upload`` connector for provenance.
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, UploadFile

from metis_core.observability import incr_parse_failure
from metis_gateway.deps import BackendDep, WorkspaceWriterDep
from metis_gateway.errors import ConflictError
from metis_gateway.schemas import ParseStatus, UploadResponse

router = APIRouter(prefix="/workspaces/{workspace_id}/upload", tags=["upload"])


@router.post("", response_model=UploadResponse, status_code=201)
async def upload_files(
    files: list[UploadFile], context: WorkspaceWriterDep, backend: BackendDep
) -> UploadResponse:
    policy = await backend.identity.get_model_policy(context.workspace.id)
    workspace = backend.workspace_for(
        context.workspace.id, allow_external=policy.allow_external_models
    )
    statuses: list[ParseStatus] = []
    for file in files:
        filename = file.filename or "upload"
        data = await file.read()
        try:
            outcome = await workspace.ingest_bytes(
                filename=filename, data=data, sensitivity=context.workspace.default_sensitivity
            )
        except ConflictError as exc:
            statuses.append(ParseStatus(filename=filename, status="unsupported", error=str(exc)))
        except Exception as exc:  # one malformed file must not fail the whole batch
            incr_parse_failure(media_type=mimetypes.guess_type(filename)[0] or "unknown")
            statuses.append(ParseStatus(filename=filename, status="failed", error=str(exc)))
        else:
            statuses.append(
                ParseStatus(
                    filename=filename,
                    status="parsed",
                    doc_id=outcome.doc_id,
                    media_type=outcome.media_type,
                    segments=outcome.segments,
                    claims=outcome.claims,
                    coverage=outcome.coverage,
                    page_count=outcome.page_count,
                    tables=outcome.tables,
                    warnings=list(outcome.warnings),
                    parse_path=outcome.parse_path,
                )
            )
    return UploadResponse(files=statuses)
