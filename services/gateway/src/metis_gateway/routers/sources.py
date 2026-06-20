"""Source management: register a connector-backed source and list configured sources.

Operators configure sources for the deployment; the source is bound to a workspace (the configured
default unless one is named) and persisted durably, so setup and sync state survive a restart and
the ingest worker reads it to know what to poll.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import ValidationError

from metis_gateway.deps import BackendDep, OperatorDep, UserDep
from metis_gateway.errors import ConflictError, NotFoundError
from metis_gateway.schemas import SourceCreate, SourceErasureView, SourceView, SyncResponse
from metis_ingestion import ConnectorScheduler
from metis_protocol import SourceConfig, SourceId, WorkspaceId, new_id

router = APIRouter(prefix="/sources", tags=["sources"])


def _view(config: SourceConfig) -> SourceView:
    return SourceView(
        id=str(config.id),
        workspace_id=str(config.workspace_id),
        name=config.name,
        connector=config.connector,
        sensitivity=config.sensitivity,
        auth_method=config.auth_method,
    )


@router.post("", response_model=SourceView, status_code=201)
async def create_source(
    body: SourceCreate, backend: BackendDep, _principal: OperatorDep
) -> SourceView:
    spec = backend.connectors.get(body.connector)
    if spec is None:
        raise ConflictError(f"unknown connector {body.connector!r}")
    try:
        # Validate the connector-specific payload (e.g. a Telegram chat) before persisting, so a
        # misconfigured source is rejected at setup rather than failing mid-sync on the worker.
        backend.connectors.validate_config(body.connector, body.config)
    except ValidationError as exc:
        raise ConflictError(f"invalid config for {body.connector!r} source") from exc
    workspace_id = WorkspaceId(body.workspace_id) if body.workspace_id else backend.workspace_id
    config = SourceConfig(
        id=new_id(SourceId),
        workspace_id=workspace_id,
        name=body.name,
        connector=body.connector,
        sensitivity=body.sensitivity,
        auth_method=spec.auth.method.value,
        created_at=datetime.now(UTC),
        config=body.config,
    )
    return _view(await backend.sources.register(config))


@router.get("", response_model=list[SourceView])
async def list_sources(backend: BackendDep, _principal: UserDep) -> list[SourceView]:
    return [_view(config) for config in await backend.sources.list_all()]


@router.post("/{source_id}/sync", response_model=SyncResponse, status_code=202)
async def sync_source(source_id: str, backend: BackendDep, _principal: OperatorDep) -> SyncResponse:
    """Enqueue a connector-sync job for the source — the ingest worker leases and runs it, so the
    source ingests end-to-end via a durable *queued* job rather than an inline call."""
    source = await backend.sources.get(SourceId(source_id))
    if source is None:
        raise NotFoundError(f"no source {source_id!r}")
    cursor = await backend.sources.get_cursor(source.id)
    job_id = await ConnectorScheduler(backend.jobs).schedule_poll(
        workspace_id=source.workspace_id,
        connector=source.connector,
        source_id=source.id,
        cursor=cursor.cursor if cursor is not None else None,
    )
    return SyncResponse(job_id=str(job_id), source_id=source_id)


@router.delete("/{source_id}", response_model=SourceErasureView)
async def delete_source(
    source_id: str, backend: BackendDep, _principal: OperatorDep
) -> SourceErasureView:
    """Delete a source: erase every artifact it produced (cascade + blob) and remove its
    registration (config, cursor, run history). Operator-gated, like source creation."""
    source = await backend.sources.get(SourceId(source_id))
    if source is None:
        raise NotFoundError(f"no source {source_id!r}")
    result = await backend.workspace_for(source.workspace_id).erase_source(str(source.id))
    await backend.sources.delete(source.id)
    return SourceErasureView(
        artifacts=result.artifacts,
        claims=result.claims,
        mem_cells=result.mem_cells,
        blobs_erased=result.blobs_erased,
    )
