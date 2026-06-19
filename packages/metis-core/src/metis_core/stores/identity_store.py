"""``PostgresIdentityStore``: organizations, users, workspaces, and memberships.

This is the control-plane store the gateway resolves a caller and their workspace access
from. :meth:`resolve_role` is the gate primitive — it returns the caller's role in a
workspace, or ``None`` when there is no membership, which is exactly the isolation boundary
that keeps one user's personal workspace invisible to another. Writes are idempotent by id,
matching the rest of the stores.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.db.session import unit_of_work
from metis_core.mappers import (
    membership_to_row,
    organization_to_row,
    to_model,
    user_to_row,
    workspace_to_row,
)
from metis_core.models import (
    OrganizationRow,
    UserRow,
    WorkspaceMembershipRow,
    WorkspaceRow,
)
from metis_protocol import (
    Organization,
    Role,
    User,
    UserId,
    Workspace,
    WorkspaceId,
    WorkspaceMembership,
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
