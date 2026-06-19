"""Source management: register a connector-backed source and list configured sources.

Operators configure sources for the deployment; the source is bound to a workspace (the configured
default unless one is named) and persisted durably, so setup and sync state survive a restart and
the ingest worker reads it to know what to poll.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, OperatorDep, UserDep
from metis_gateway.errors import ConflictError
from metis_gateway.schemas import SourceCreate, SourceView
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
    workspace_id = WorkspaceId(body.workspace_id) if body.workspace_id else backend.workspace_id
    config = SourceConfig(
        id=new_id(SourceId),
        workspace_id=workspace_id,
        name=body.name,
        connector=body.connector,
        sensitivity=body.sensitivity,
        auth_method=spec.auth.method.value,
        created_at=datetime.now(UTC),
    )
    return _view(await backend.sources.register(config))


@router.get("", response_model=list[SourceView])
async def list_sources(backend: BackendDep, _principal: UserDep) -> list[SourceView]:
    return [_view(config) for config in await backend.sources.list_all()]
