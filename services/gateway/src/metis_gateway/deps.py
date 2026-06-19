"""FastAPI dependency aliases: the backend container and the two auth scopes.

Using ``Annotated[..., Depends(...)]`` keeps router signatures clean and type-checked (no
``Depends`` default values), and centralizes how a request reaches the backend and its principal.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from metis_gateway.auth import (
    Principal,
    WorkspaceContext,
    current_user,
    require_operator,
    require_user,
    workspace_context,
)
from metis_gateway.backend import Backend
from metis_protocol import User


def get_backend(request: Request) -> Backend:
    backend: Backend = request.app.state.backend
    return backend


BackendDep = Annotated[Backend, Depends(get_backend)]
UserDep = Annotated[Principal, Depends(require_user)]
OperatorDep = Annotated[Principal, Depends(require_operator)]

# Identity-backed: the calling User, and the workspace membership gate at three capability tiers.
CurrentUserDep = Annotated[User, Depends(current_user)]
MemberDep = Annotated[WorkspaceContext, Depends(workspace_context())]
WorkspaceWriterDep = Annotated[WorkspaceContext, Depends(workspace_context(write=True))]
WorkspaceAdminDep = Annotated[WorkspaceContext, Depends(workspace_context(admin=True))]
