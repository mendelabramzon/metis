"""Invite links: a workspace admin mints one; an invitee redeems it (unauthenticated).

Minting is admin-gated on the target workspace; redeeming is open (the token is the secret).
Redeeming provisions the invitee's user + personal workspace and a membership in the invited
workspace, then stamps the invite redeemed (single-use). The returned id is the new user's bearer
token (a dev stand-in; sessions/SSO are Stage 14).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, WorkspaceAdminDep
from metis_gateway.errors import ConflictError, NotFoundError
from metis_gateway.routers.users import provision_user
from metis_gateway.schemas import InviteCreate, InviteRedeem, InviteRedeemView, InviteView
from metis_protocol import Invite, InviteId, MembershipId, WorkspaceMembership, new_id

router = APIRouter(tags=["invites"])


@router.post("/workspaces/{workspace_id}/invites", response_model=InviteView, status_code=201)
async def create_invite(
    body: InviteCreate, context: WorkspaceAdminDep, backend: BackendDep
) -> InviteView:
    """Mint a single-use invite to this workspace and its organization (admin-gated)."""
    invite = await backend.identity.create_invite(
        Invite(
            id=new_id(InviteId),
            organization_id=context.workspace.organization_id,
            workspace_id=context.workspace.id,
            role=body.role,
            token=secrets.token_urlsafe(24),
            created_by=context.user.id,
            created_at=datetime.now(UTC),
        )
    )
    return InviteView(
        id=str(invite.id),
        workspace_id=str(invite.workspace_id),
        role=invite.role,
        token=invite.token,
        redeemed=invite.redeemed_by is not None,
    )


@router.post("/invites/{token}/redeem", response_model=InviteRedeemView)
async def redeem_invite(token: str, body: InviteRedeem, backend: BackendDep) -> InviteRedeemView:
    """Redeem an invite (no auth): provision the user + personal workspace, join the invited
    workspace, and stamp it redeemed. The returned ``user_id`` is the caller's bearer token."""
    invite = await backend.identity.get_invite_by_token(token)
    if invite is None:
        raise NotFoundError("unknown or invalid invite")
    if invite.redeemed_by is not None:
        raise ConflictError("this invite has already been redeemed")
    if await backend.identity.get_user_by_email(body.email) is not None:
        raise ConflictError(f"a user with email {body.email!r} already exists")
    user = await provision_user(
        backend,
        organization_id=invite.organization_id,
        email=body.email,
        display_name=body.display_name,
    )
    await backend.identity.add_membership(
        WorkspaceMembership(
            id=new_id(MembershipId),
            workspace_id=invite.workspace_id,
            user_id=user.id,
            role=invite.role,
            created_at=datetime.now(UTC),
        )
    )
    await backend.identity.mark_invite_redeemed(invite.id, user_id=user.id)
    return InviteRedeemView(
        user_id=str(user.id),
        organization_id=str(user.organization_id),
        workspace_id=str(invite.workspace_id),
    )
