"""FastAPI dependency aliases: the backend container and the two auth scopes.

Using ``Annotated[..., Depends(...)]`` keeps router signatures clean and type-checked (no
``Depends`` default values), and centralizes how a request reaches the backend and its principal.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from metis_gateway.auth import Principal, require_operator, require_user
from metis_gateway.backend import Backend


def get_backend(request: Request) -> Backend:
    backend: Backend = request.app.state.backend
    return backend


BackendDep = Annotated[Backend, Depends(get_backend)]
UserDep = Annotated[Principal, Depends(require_user)]
OperatorDep = Annotated[Principal, Depends(require_operator)]
