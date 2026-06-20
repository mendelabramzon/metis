"""Proposed-action command surface: interpret a free-text command into a typed action, list/inspect
the proposals, and approve/reject them.

The "human agency over side effects" invariant in HTTP form: a command is interpreted into a typed
ProposedAction that is persisted and shown (with its risk tier, summary, sensitivity, and audit
target) before any effectful execution. Approving/rejecting records the decision and actor.
Executing the approved action against the underlying engines is a separate, risk-gated step.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from metis_gateway.actions import interpret_command
from metis_gateway.deps import BackendDep, UserDep
from metis_gateway.errors import ConflictError, NotFoundError
from metis_gateway.schemas import CommandRequest, DecisionRequest, ProposedActionView
from metis_protocol import ActionId, ActionStatus, ProposedAction, Sensitivity, WorkspaceId

router = APIRouter(prefix="/actions", tags=["actions"])


def _view(action: ProposedAction) -> ProposedActionView:
    return ProposedActionView(
        id=str(action.id),
        workspace_id=str(action.workspace_id),
        kind=action.kind,
        risk=action.risk,
        command=action.command,
        summary=action.summary,
        parameters=action.parameters,
        sensitivity=action.sensitivity,
        audit_target=action.audit_target,
        status=action.status,
        decided_by=action.decided_by,
        decision_note=action.decision_note,
    )


def _workspace(body_workspace_id: str | None, backend: BackendDep) -> WorkspaceId:
    return WorkspaceId(body_workspace_id) if body_workspace_id else backend.workspace_id


@router.post("", response_model=ProposedActionView, status_code=201)
async def propose_action(
    body: CommandRequest, backend: BackendDep, _principal: UserDep
) -> ProposedActionView:
    """Interpret a command into a typed proposed action and persist it — shown before execution."""
    action = await interpret_command(
        body.command,
        workspace_id=_workspace(body.workspace_id, backend),
        sensitivity=Sensitivity.INTERNAL,
        caller=backend.model_caller,
    )
    return _view(await backend.actions.propose(action))


@router.get("", response_model=list[ProposedActionView])
async def list_actions(
    backend: BackendDep, _principal: UserDep, status: ActionStatus | None = None
) -> list[ProposedActionView]:
    """Proposed actions, newest first; filter the inbox with ``?status=``."""
    return [_view(a) for a in await backend.actions.list(backend.workspace_id, status=status)]


@router.get("/{action_id}", response_model=ProposedActionView)
async def get_action(
    action_id: str, backend: BackendDep, _principal: UserDep
) -> ProposedActionView:
    action = await backend.actions.get(ActionId(action_id))
    if action is None:
        raise NotFoundError(f"no action {action_id!r}")
    return _view(action)


async def _decide(
    action_id: str, backend: BackendDep, actor: str, *, approved: bool, note: str
) -> ProposedAction:
    action = await backend.actions.get(ActionId(action_id))
    if action is None:
        raise NotFoundError(f"no action {action_id!r}")
    if action.status is not ActionStatus.PROPOSED:
        raise ConflictError(f"action {action_id!r} is already {action.status.value}")
    decided = action.model_copy(
        update={
            "status": ActionStatus.APPROVED if approved else ActionStatus.REJECTED,
            "decided_by": actor,
            "decided_at": datetime.now(UTC),
            "decision_note": note,
        }
    )
    return await backend.actions.update(decided)


@router.post("/{action_id}/approve", response_model=ProposedActionView)
async def approve_action(
    action_id: str, body: DecisionRequest, backend: BackendDep, principal: UserDep
) -> ProposedActionView:
    """Approve a proposed action (recording the actor); executing it is a separate gated step."""
    return _view(
        await _decide(action_id, backend, principal.subject, approved=True, note=body.note)
    )


@router.post("/{action_id}/reject", response_model=ProposedActionView)
async def reject_action(
    action_id: str, body: DecisionRequest, backend: BackendDep, principal: UserDep
) -> ProposedActionView:
    return _view(
        await _decide(action_id, backend, principal.subject, approved=False, note=body.note)
    )
