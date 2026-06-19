"""Approval inbox: one queue over agent/skill actions and wiki patches; approving is audited."""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.backend import InboxItem
from metis_gateway.deps import BackendDep, OperatorDep
from metis_gateway.schemas import ApproveRequest, InboxItemView

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _view(item: InboxItem) -> InboxItemView:
    return InboxItemView(kind=item.kind, id=item.id, summary=item.summary, status=item.status)


@router.get("", response_model=list[InboxItemView])
async def inbox(backend: BackendDep, _principal: OperatorDep) -> list[InboxItemView]:
    return [_view(item) for item in await backend.inbox.pending()]


@router.post("/{kind}/{item_id}/approve", response_model=InboxItemView)
async def approve(
    kind: str, item_id: str, body: ApproveRequest, backend: BackendDep, _principal: OperatorDep
) -> InboxItemView:
    return _view(await backend.inbox.approve(kind=kind, item_id=item_id, note=body.note))
