"""Source management: register a connector-backed source and list configured sources."""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.backend import SourceConfig
from metis_gateway.deps import BackendDep, OperatorDep, UserDep
from metis_gateway.schemas import SourceCreate, SourceView

router = APIRouter(prefix="/sources", tags=["sources"])


def _view(config: SourceConfig) -> SourceView:
    return SourceView(
        id=config.id,
        name=config.name,
        connector=config.connector,
        sensitivity=config.sensitivity,
        auth_method=config.auth_method,
    )


@router.post("", response_model=SourceView, status_code=201)
async def create_source(
    body: SourceCreate, backend: BackendDep, _principal: OperatorDep
) -> SourceView:
    return _view(
        backend.sources.register(
            name=body.name, connector=body.connector, sensitivity=body.sensitivity
        )
    )


@router.get("", response_model=list[SourceView])
async def list_sources(backend: BackendDep, _principal: UserDep) -> list[SourceView]:
    return [_view(config) for config in backend.sources.list()]
