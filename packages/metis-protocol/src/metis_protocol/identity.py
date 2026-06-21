"""Identity and tenancy: Organization, User, Workspace, and WorkspaceMembership.

These are control-plane entities, not evidence artifacts: they carry no provenance or
source spans, so they extend :class:`VersionedModel` rather than ``Artifact``. Storage
already scopes every artifact by ``workspace_id``; this module adds the identity that the
gateway resolves a caller and their membership from, so retrieval can be gated by
membership *before* it touches spans, claims, memory, or wiki pages.
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field

from metis_protocol.enums import Role, Sensitivity, WorkspaceKind
from metis_protocol.ids import InviteId, MembershipId, OrganizationId, UserId, WorkspaceId
from metis_protocol.versioning import VersionedModel, schema


@schema
class Organization(VersionedModel):
    """A tenant: the top-level owner of users and workspaces."""

    id: OrganizationId
    name: str
    created_at: AwareDatetime


@schema
class User(VersionedModel):
    """A person in an organization; the actor identity recorded on audit events."""

    id: UserId
    organization_id: OrganizationId
    email: str
    display_name: str
    created_at: AwareDatetime
    active: bool = True


@schema
class Workspace(VersionedModel):
    """A personal or shared context boundary; every artifact is scoped to one of these.

    ``owner_id`` is set for a personal workspace (its single owner). ``default_sensitivity``
    is the floor stamped on artifacts ingested into the workspace absent a stricter source
    ACL.
    """

    id: WorkspaceId
    organization_id: OrganizationId
    kind: WorkspaceKind
    name: str
    owner_id: UserId | None = None
    default_sensitivity: Sensitivity = Sensitivity.INTERNAL
    created_at: AwareDatetime


@schema
class WorkspaceMembership(VersionedModel):
    """A user's role in a workspace — the unit the retrieval/access gate checks.

    Its absence is the isolation boundary: no membership means no access, which is how one
    user's personal workspace stays invisible to another.
    """

    id: MembershipId
    workspace_id: WorkspaceId
    user_id: UserId
    role: Role
    created_at: AwareDatetime


class WorkspaceModelPolicy(VersionedModel):
    """Per-workspace model-routing policy: whether the workspace's data may use external providers,
    and an optional daily model-spend cap. Absent a stored policy, the default below applies
    (external allowed, no cap). This is mutable operational config, not an audited artifact, so it
    is not registered in the schema snapshot set.
    """

    workspace_id: WorkspaceId
    allow_external_models: bool = True
    daily_cost_cap_usd: float | None = Field(default=None, ge=0.0)


class Invite(VersionedModel):
    """A single-use link to join an organization and one of its shared workspaces.

    Redeeming it provisions the invitee's user + personal workspace and a membership in
    ``workspace_id`` with ``role``. Operational, single-use control-plane state (like
    ``WorkspaceModelPolicy``), so it is not registered in the schema snapshot set.
    """

    id: InviteId
    organization_id: OrganizationId
    workspace_id: WorkspaceId
    role: Role = Role.MEMBER
    token: str
    created_by: UserId
    created_at: AwareDatetime
    redeemed_by: UserId | None = None
    redeemed_at: AwareDatetime | None = None
