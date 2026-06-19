"""Identity provisioning: organizations and users (operator-gated), plus 'who am I'.

A new user is provisioned with a personal workspace and an owner membership, so the identity graph
the workspace gate reads is never empty. Real sessions/SSO are Stage 14 — the bearer token is the
user's id (a dev stand-in); see ``auth.current_user``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, CurrentUserDep, OperatorDep
from metis_gateway.errors import ConflictError
from metis_gateway.schemas import (
    OrganizationCreate,
    OrganizationView,
    UserCreate,
    UserView,
)
from metis_protocol import (
    MembershipId,
    Organization,
    OrganizationId,
    Role,
    User,
    UserId,
    Workspace,
    WorkspaceId,
    WorkspaceKind,
    WorkspaceMembership,
    new_id,
)

router = APIRouter(tags=["identity"])


def _user_view(user: User) -> UserView:
    return UserView(
        id=str(user.id),
        organization_id=str(user.organization_id),
        email=user.email,
        display_name=user.display_name,
        active=user.active,
    )


@router.post("/organizations", response_model=OrganizationView, status_code=201)
async def create_organization(
    body: OrganizationCreate, backend: BackendDep, _principal: OperatorDep
) -> OrganizationView:
    org = await backend.identity.create_organization(
        Organization(id=new_id(OrganizationId), name=body.name, created_at=datetime.now(UTC))
    )
    return OrganizationView(id=str(org.id), name=org.name)


@router.post("/users", response_model=UserView, status_code=201)
async def create_user(body: UserCreate, backend: BackendDep, _principal: OperatorDep) -> UserView:
    if await backend.identity.get_user_by_email(body.email) is not None:
        raise ConflictError(f"a user with email {body.email!r} already exists")
    now = datetime.now(UTC)
    org_id = OrganizationId(body.organization_id)
    user = await backend.identity.create_user(
        User(
            id=new_id(UserId),
            organization_id=org_id,
            email=body.email,
            display_name=body.display_name,
            created_at=now,
        )
    )
    # Every user gets a personal workspace they own — the default home for their context.
    workspace = await backend.identity.create_workspace(
        Workspace(
            id=new_id(WorkspaceId),
            organization_id=org_id,
            kind=WorkspaceKind.PERSONAL,
            name=f"{user.display_name} (personal)",
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
    return _user_view(user)


@router.get("/users/me", response_model=UserView)
async def me(user: CurrentUserDep) -> UserView:
    return _user_view(user)
