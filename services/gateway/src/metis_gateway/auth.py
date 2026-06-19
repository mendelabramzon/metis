"""API authentication and scopes, enforced at the boundary.

Two scopes — ``user`` (query/read) and ``operator`` (approvals, jobs, audit) — keyed off a bearer
token. The scope also caps what a caller may see: a user is bounded to ``INTERNAL`` data, an
operator to ``RESTRICTED``, so sensitivity is enforced here, before a request reaches the engine.
Token-to-scope is a dev stand-in; encrypted credentials and SSO are Stage 14, but the seam (a
``Principal`` resolved per request) is in place.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import IntEnum
from typing import Annotated

from fastapi import Depends, Header, Request

from metis_core.policy import workspace_access_decision
from metis_gateway.backend import Backend
from metis_gateway.errors import ForbiddenError, NotFoundError, UnauthorizedError
from metis_gateway.settings import GatewaySettings
from metis_protocol import Role, Sensitivity, User, UserId, WorkspaceId
from metis_protocol import Workspace as WorkspaceEntity


class Scope(IntEnum):
    """Ordered so a higher scope satisfies a lower requirement."""

    USER = 1
    OPERATOR = 2


@dataclass(frozen=True)
class Principal:
    subject: str
    scope: Scope
    max_sensitivity: Sensitivity


def _settings(request: Request) -> GatewaySettings:
    settings: GatewaySettings = request.app.state.settings
    return settings


def _principal_for_token(token: str, settings: GatewaySettings) -> Principal | None:
    if token == settings.operator_token:
        return Principal("operator", Scope.OPERATOR, Sensitivity.RESTRICTED)
    if token == settings.user_token:
        return Principal("user", Scope.USER, Sensitivity.INTERNAL)
    return None


def authenticate(request: Request, authorization: str | None = Header(default=None)) -> Principal:
    """Resolve the caller from the ``Authorization: Bearer <token>`` header (401 if unresolved)."""
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("expected 'Authorization: Bearer <token>'")
    principal = _principal_for_token(authorization[7:].strip(), _settings(request))
    if principal is None:
        raise UnauthorizedError()
    return principal


def require(min_scope: Scope) -> Callable[[Principal], Principal]:
    """A dependency factory that admits only principals at or above ``min_scope``."""

    def _dependency(principal: Annotated[Principal, Depends(authenticate)]) -> Principal:
        if principal.scope < min_scope:
            raise ForbiddenError(f"requires {min_scope.name.lower()} scope")
        return principal

    return _dependency


require_user = require(Scope.USER)
require_operator = require(Scope.OPERATOR)


# --- identity-backed auth: a real User + the workspace membership gate -------------------------


async def current_user(request: Request, authorization: str | None = Header(default=None)) -> User:
    """Resolve the calling ``User`` from the bearer token.

    The token is the user's id — a dev stand-in for a real session (sessions/SSO are Stage 14); the
    seam (a ``User`` resolved per request from the identity store) is what matters. 401 if the token
    is absent, malformed, or unknown.
    """
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("expected 'Authorization: Bearer <token>'")
    backend: Backend = request.app.state.backend
    user = await backend.identity.get_user(UserId(authorization[7:].strip()))
    if user is None:
        raise UnauthorizedError()
    return user


@dataclass(frozen=True)
class WorkspaceContext:
    """A caller resolved against a workspace: their identity, the workspace, and admitted role."""

    user: User
    workspace: WorkspaceEntity
    role: Role


def workspace_context(
    *, write: bool = False, admin: bool = False
) -> Callable[..., Awaitable[WorkspaceContext]]:
    """A dependency factory enforcing the membership gate on the ``{workspace_id}`` path param.

    No membership -> 403 (the isolation boundary); an insufficient role for a write/admin op -> 403;
    an unknown workspace -> 404. Returns the resolved :class:`WorkspaceContext` on success. Policy
    lives in the pure ``workspace_access_decision``, not in this handler.
    """

    async def _dependency(
        workspace_id: str,
        request: Request,
        user: Annotated[User, Depends(current_user)],
    ) -> WorkspaceContext:
        backend: Backend = request.app.state.backend
        ws_id = WorkspaceId(workspace_id)
        workspace = await backend.identity.get_workspace(ws_id)
        if workspace is None:
            raise NotFoundError(f"unknown workspace {workspace_id}")
        role = await backend.identity.resolve_role(user_id=user.id, workspace_id=ws_id)
        decision = workspace_access_decision(role, require_write=write, require_admin=admin)
        if not decision.allowed:
            raise ForbiddenError(decision.reason)
        assert role is not None  # decision.allowed implies a resolved role
        return WorkspaceContext(user=user, workspace=workspace, role=role)

    return _dependency
