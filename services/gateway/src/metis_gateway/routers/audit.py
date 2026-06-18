"""Audit/event view: the operator's window into model calls, skill runs, and approvals."""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, OperatorDep
from metis_gateway.schemas import AuditView
from metis_protocol import AuditEvent

router = APIRouter(prefix="/audit", tags=["audit"])


def _view(event: AuditEvent) -> AuditView:
    return AuditView(
        id=str(event.id),
        action=event.action,
        actor=event.actor.agent,
        target_id=event.target_id,
        target_kind=event.target_kind,
        sensitivity=event.sensitivity.value if event.sensitivity is not None else None,
        occurred_at=event.occurred_at.isoformat(),
    )


@router.get("", response_model=list[AuditView])
async def list_audit(
    backend: BackendDep,
    _principal: OperatorDep,
    action: str | None = None,
    limit: int = 100,
) -> list[AuditView]:
    return [_view(event) for event in await backend.audit.recent(action=action, limit=limit)]
