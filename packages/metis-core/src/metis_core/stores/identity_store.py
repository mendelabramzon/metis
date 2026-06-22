"""``PostgresIdentityStore``: organizations, users, workspaces, and memberships.

This is the control-plane store the gateway resolves a caller and their workspace access
from. :meth:`resolve_role` is the gate primitive — it returns the caller's role in a
workspace, or ``None`` when there is no membership, which is exactly the isolation boundary
that keeps one user's personal workspace invisible to another. Writes are idempotent by id,
matching the rest of the stores.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.db.session import unit_of_work
from metis_core.mappers import (
    invite_to_row,
    membership_to_row,
    model_policy_to_row,
    organization_to_row,
    to_model,
    user_to_row,
    workspace_to_row,
)
from metis_core.models import (
    InviteRow,
    OrganizationRow,
    UserRow,
    WorkspaceMembershipRow,
    WorkspaceModelPolicyRow,
    WorkspaceRow,
)
from metis_protocol import (
    Invite,
    InviteId,
    Organization,
    Role,
    User,
    UserId,
    Workspace,
    WorkspaceId,
    WorkspaceMembership,
    WorkspaceModelPolicy,
)


class PostgresIdentityStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    # --- writes (idempotent by id) ------------------------------------------------------

    async def create_organization(self, org: Organization) -> Organization:
        async with unit_of_work(self._sessionmaker) as session:
            existing = await session.get(OrganizationRow, str(org.id))
            if existing is not None:
                return to_model(existing, Organization)
            session.add(organization_to_row(org))
        return org

    async def create_user(self, user: User) -> User:
        async with unit_of_work(self._sessionmaker) as session:
            existing = await session.get(UserRow, str(user.id))
            if existing is not None:
                return to_model(existing, User)
            session.add(user_to_row(user))
        return user

    async def create_workspace(self, workspace: Workspace) -> Workspace:
        async with unit_of_work(self._sessionmaker) as session:
            existing = await session.get(WorkspaceRow, str(workspace.id))
            if existing is not None:
                return to_model(existing, Workspace)
            session.add(workspace_to_row(workspace))
        return workspace

    async def add_membership(self, membership: WorkspaceMembership) -> WorkspaceMembership:
        async with unit_of_work(self._sessionmaker) as session:
            existing = await session.get(WorkspaceMembershipRow, str(membership.id))
            if existing is not None:
                return to_model(existing, WorkspaceMembership)
            session.add(membership_to_row(membership))
        return membership

    # --- reads --------------------------------------------------------------------------

    async def get_user(self, user_id: UserId) -> User | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(UserRow, str(user_id))
        return to_model(row, User) if row is not None else None

    async def get_user_by_email(self, email: str) -> User | None:
        stmt = select(UserRow).where(UserRow.email == email)
        async with unit_of_work(self._sessionmaker) as session:
            row = (await session.scalars(stmt)).first()
        return to_model(row, User) if row is not None else None

    async def list_users(self) -> Sequence[User]:
        """Every user, oldest first — the pre-auth sign-in selector (C2). Active filtering is the
        caller's concern (the selector only offers active accounts)."""
        stmt = select(UserRow).order_by(UserRow.created_at.asc())
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [to_model(row, User) for row in rows]

    async def get_workspace(self, workspace_id: WorkspaceId) -> Workspace | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(WorkspaceRow, str(workspace_id))
        return to_model(row, Workspace) if row is not None else None

    async def resolve_role(self, *, user_id: UserId, workspace_id: WorkspaceId) -> Role | None:
        """The caller's role in the workspace, or ``None`` if they are not a member."""
        stmt = select(WorkspaceMembershipRow.role).where(
            WorkspaceMembershipRow.workspace_id == str(workspace_id),
            WorkspaceMembershipRow.user_id == str(user_id),
        )
        async with unit_of_work(self._sessionmaker) as session:
            role = (await session.scalars(stmt)).first()
        return Role(role) if role is not None else None

    async def workspaces_for_user(self, user_id: UserId) -> Sequence[Workspace]:
        """Every workspace the user is a member of, oldest first (the workspace switcher)."""
        stmt = (
            select(WorkspaceRow)
            .join(WorkspaceMembershipRow, WorkspaceMembershipRow.workspace_id == WorkspaceRow.id)
            .where(WorkspaceMembershipRow.user_id == str(user_id))
            .order_by(WorkspaceRow.created_at.asc())
        )
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [to_model(row, Workspace) for row in rows]

    async def members_of(self, workspace_id: WorkspaceId) -> Sequence[WorkspaceMembership]:
        """Every membership in the workspace, oldest first."""
        stmt = (
            select(WorkspaceMembershipRow)
            .where(WorkspaceMembershipRow.workspace_id == str(workspace_id))
            .order_by(WorkspaceMembershipRow.created_at.asc())
        )
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [to_model(row, WorkspaceMembership) for row in rows]

    async def get_model_policy(self, workspace_id: WorkspaceId) -> WorkspaceModelPolicy:
        """The workspace's model policy, or the permissive default if none is stored."""
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(WorkspaceModelPolicyRow, str(workspace_id))
        if row is None:
            return WorkspaceModelPolicy(workspace_id=workspace_id)
        return to_model(row, WorkspaceModelPolicy)

    async def set_model_policy(self, policy: WorkspaceModelPolicy) -> WorkspaceModelPolicy:
        """Upsert the workspace's model policy (mutable config, unlike the append-only stores)."""
        async with unit_of_work(self._sessionmaker) as session:
            existing = await session.get(WorkspaceModelPolicyRow, str(policy.workspace_id))
            if existing is None:
                session.add(model_policy_to_row(policy))
            else:
                existing.schema_version = policy.schema_version
                existing.allow_external_models = policy.allow_external_models
                existing.daily_cost_cap_usd = policy.daily_cost_cap_usd
                existing.body = policy.model_dump(mode="json")
        return policy

    async def deactivate_user(self, user_id: UserId) -> User | None:
        """Soft-disable a user (active=False) so the auth boundary rejects them; the audit trail
        stays. ``active`` lives in the body, so rewrite it. Returns the user, or None if unknown."""
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(UserRow, str(user_id))
            if row is None:
                return None
            user = to_model(row, User).model_copy(update={"active": False})
            row.body = user.model_dump(mode="json")
        return user

    async def set_weekly_digest_opt_in(self, user_id: UserId, *, enabled: bool) -> User | None:
        """Toggle the user's weekly-digest preference (A7). Lives in the body, so rewrite it.
        Returns the updated user, or None if unknown."""
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(UserRow, str(user_id))
            if row is None:
                return None
            user = to_model(row, User).model_copy(update={"weekly_digest_opt_in": enabled})
            row.body = user.model_dump(mode="json")
        return user

    async def create_invite(self, invite: Invite) -> Invite:
        async with unit_of_work(self._sessionmaker) as session:
            existing = await session.get(InviteRow, str(invite.id))
            if existing is not None:
                return to_model(existing, Invite)
            session.add(invite_to_row(invite))
        return invite

    async def get_invite_by_token(self, token: str) -> Invite | None:
        stmt = select(InviteRow).where(InviteRow.token == token)
        async with unit_of_work(self._sessionmaker) as session:
            row = (await session.scalars(stmt)).first()
        return to_model(row, Invite) if row is not None else None

    async def mark_invite_redeemed(self, invite_id: InviteId, *, user_id: UserId) -> Invite | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(InviteRow, str(invite_id))
            if row is None:
                return None
            invite = to_model(row, Invite).model_copy(
                update={"redeemed_by": user_id, "redeemed_at": datetime.now(UTC)}
            )
            row.body = invite.model_dump(mode="json")
        return invite
