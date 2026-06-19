"""Ingestion: push content for a source through the (real) extractor into evidence."""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, OperatorDep
from metis_gateway.errors import NotFoundError
from metis_gateway.schemas import IngestRequest, IngestResponse
from metis_protocol import SourceId

router = APIRouter(prefix="/sources/{source_id}/ingest", tags=["ingestion"])


@router.post("", response_model=IngestResponse, status_code=202)
async def ingest(
    source_id: str, body: IngestRequest, backend: BackendDep, _principal: OperatorDep
) -> IngestResponse:
    source = await backend.sources.get(SourceId(source_id))
    if source is None:
        raise NotFoundError(f"no source {source_id!r}")
    sensitivity = body.sensitivity if body.sensitivity is not None else source.sensitivity
    doc_id, claims = await backend.workspace.ingest(
        filename=body.filename, content=body.content, sensitivity=sensitivity
    )
    return IngestResponse(doc_id=doc_id, artifacts=1, claims=claims)
