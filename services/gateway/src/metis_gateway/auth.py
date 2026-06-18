"""API authentication and scopes, enforced at the boundary.

Two scopes — ``user`` (query/read) and ``operator`` (approvals, jobs, audit) — keyed off a bearer
token. The scope also caps what a caller may see: a user is bounded to ``INTERNAL`` data, an
operator to ``RESTRICTED``, so sensitivity is enforced here, before a request reaches the engine.
Token-to-scope is a dev stand-in; encrypted credentials and SSO are Stage 14, but the seam (a
``Principal`` resolved per request) is in place.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from typing import Annotated

from fastapi import Depends, Header, Request

from metis_gateway.errors import ForbiddenError, UnauthorizedError
from metis_gateway.settings import GatewaySettings
from metis_protocol import Sensitivity


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
