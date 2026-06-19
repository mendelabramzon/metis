"""PostgresIdentityStore: membership resolution is the workspace isolation gate.

The load-bearing test is ``test_personal_workspace_is_isolated_from_other_users`` — it proves
that a real user in the same organization has no role in another user's personal workspace, so
``resolve_role`` returns ``None`` and any access decision built on it denies. Live connectors do
not turn on until this holds (server-deployment Stage 1, the first hard gate).
"""

from __future__ import annotations

from datetime import UTC, datetime

from metis_core.stores import PostgresIdentityStore
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

_T = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _org() -> Organization:
    return Organization(id=new_id(OrganizationId), name="Acme", created_at=_T)


def _user(org: Organization, email: str) -> User:
    return User(
        id=new_id(UserId),
        organization_id=org.id,
        email=email,
        display_name=email.split("@", 1)[0],
        created_at=_T,
    )


def _personal_ws(org: Organization, owner: User) -> Workspace:
    return Workspace(
        id=new_id(WorkspaceId),
        organization_id=org.id,
        kind=WorkspaceKind.PERSONAL,
        name=f"{owner.display_name} (personal)",
        owner_id=owner.id,
        created_at=_T,
    )


def _membership(ws: Workspace, user: User, role: Role) -> WorkspaceMembership:
    return WorkspaceMembership(
        id=new_id(MembershipId),
        workspace_id=ws.id,
        user_id=user.id,
        role=role,
        created_at=_T,
    )


async def test_resolve_role_returns_the_members_role(sessionmaker):
    store = PostgresIdentityStore(sessionmaker)
    org = await store.create_organization(_org())
    ada = await store.create_user(_user(org, "ada@acme.example"))
    ws = await store.create_workspace(_personal_ws(org, ada))
    await store.add_membership(_membership(ws, ada, Role.OWNER))

    assert await store.resolve_role(user_id=ada.id, workspace_id=ws.id) is Role.OWNER


async def test_personal_workspace_is_isolated_from_other_users(sessionmaker):
    store = PostgresIdentityStore(sessionmaker)
    org = await store.create_organization(_org())
    ada = await store.create_user(_user(org, "ada@acme.example"))
    grace = await store.create_user(_user(org, "grace@acme.example"))
    ada_ws = await store.create_workspace(_personal_ws(org, ada))
    await store.add_membership(_membership(ada_ws, ada, Role.OWNER))

    # Grace is a real user in the same org but was never added to Ada's workspace.
    assert await store.resolve_role(user_id=grace.id, workspace_id=ada_ws.id) is None


async def test_workspaces_for_user_lists_only_memberships(sessionmaker):
    store = PostgresIdentityStore(sessionmaker)
    org = await store.create_organization(_org())
    ada = await store.create_user(_user(org, "ada@acme.example"))
    grace = await store.create_user(_user(org, "grace@acme.example"))
    ada_ws = await store.create_workspace(_personal_ws(org, ada))
    grace_ws = await store.create_workspace(_personal_ws(org, grace))
    await store.add_membership(_membership(ada_ws, ada, Role.OWNER))
    await store.add_membership(_membership(grace_ws, grace, Role.OWNER))

    assert [w.id for w in await store.workspaces_for_user(ada.id)] == [ada_ws.id]


async def test_get_user_by_email(sessionmaker):
    store = PostgresIdentityStore(sessionmaker)
    org = await store.create_organization(_org())
    ada = await store.create_user(_user(org, "ada@acme.example"))

    found = await store.get_user_by_email("ada@acme.example")
    assert found is not None
    assert found.id == ada.id


async def test_create_is_idempotent_by_id(sessionmaker):
    store = PostgresIdentityStore(sessionmaker)
    org = _org()
    first = await store.create_organization(org)
    second = await store.create_organization(org)  # same id -> no duplicate, returns stored
    assert first.id == second.id
