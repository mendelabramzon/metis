"""Workspaces: list mine, create a shared one, and the membership-gated read/admin endpoints.

``GET /workspaces/{id}`` is the isolation gate in action — a non-member gets 403, which is how one
user's personal workspace stays invisible to another (see ``auth.workspace_context``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, CurrentUserDep, MemberDep, WorkspaceAdminDep
from metis_gateway.errors import NotFoundError
from metis_gateway.schemas import (
    MembershipCreate,
    MembershipView,
    WorkspaceCreate,
    WorkspaceView,
)
from metis_protocol import (
    MembershipId,
    Role,
    UserId,
    Workspace,
    WorkspaceId,
    WorkspaceMembership,
    new_id,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _workspace_view(workspace: Workspace) -> WorkspaceView:
    return WorkspaceView(
        id=str(workspace.id),
        organization_id=str(workspace.organization_id),
        kind=workspace.kind,
        name=workspace.name,
        owner_id=str(workspace.owner_id) if workspace.owner_id is not None else None,
        default_sensitivity=workspace.default_sensitivity,
    )


def _membership_view(membership: WorkspaceMembership) -> MembershipView:
    return MembershipView(
        id=str(membership.id),
        workspace_id=str(membership.workspace_id),
        user_id=str(membership.user_id),
        role=membership.role,
    )


@router.get("", response_model=list[WorkspaceView])
async def my_workspaces(backend: BackendDep, user: CurrentUserDep) -> list[WorkspaceView]:
    return [_workspace_view(w) for w in await backend.identity.workspaces_for_user(user.id)]


@router.post("", response_model=WorkspaceView, status_code=201)
async def create_workspace(
    body: WorkspaceCreate, backend: BackendDep, user: CurrentUserDep
) -> WorkspaceView:
    now = datetime.now(UTC)
    workspace = await backend.identity.create_workspace(
        Workspace(
            id=new_id(WorkspaceId),
            organization_id=user.organization_id,
            kind=body.kind,
            name=body.name,
            owner_id=user.id,
            created_at=now,
        )
    )
    await backend.identity.add_membership(
        WorkspaceMembership(
            id=new_id(MembershipId),
            workspace_id=workspace.id,
            user_id=user.id,
            role=Role.OWNER,
            created_at=now,
        )
    )
    return _workspace_view(workspace)


@router.get("/{workspace_id}", response_model=WorkspaceView)
async def get_workspace(context: MemberDep) -> WorkspaceView:
    return _workspace_view(context.workspace)


@router.get("/{workspace_id}/members", response_model=list[MembershipView])
async def list_members(context: WorkspaceAdminDep, backend: BackendDep) -> list[MembershipView]:
    members = await backend.identity.members_of(context.workspace.id)
    return [_membership_view(m) for m in members]


@router.post("/{workspace_id}/members", response_model=MembershipView, status_code=201)
async def add_member(
    body: MembershipCreate, context: WorkspaceAdminDep, backend: BackendDep
) -> MembershipView:
    target = await backend.identity.get_user(UserId(body.user_id))
    if target is None:
        raise NotFoundError(f"unknown user {body.user_id}")
    membership = await backend.identity.add_membership(
        WorkspaceMembership(
            id=new_id(MembershipId),
            workspace_id=context.workspace.id,
            user_id=target.id,
            role=body.role,
            created_at=datetime.now(UTC),
        )
    )
    return _membership_view(membership)
