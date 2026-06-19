"""Google OAuth consent flow: start a connect, then store the resulting refresh token.

``GET /oauth/{connector}/authorize`` returns the Google consent URL plus a CSRF ``state``. After the
user consents, Google redirects to ``GET /oauth/callback?code=&state=``, which exchanges the code
and writes the refresh token (and client secret) into the encrypted credential store under the
connector's namespace — exactly what the ingest worker resolves to sync it. The flow is
operator-scoped, and the code→tokens exchange is an injectable dependency, so the suite drives it
with no live Google.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from secrets import token_urlsafe
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request

from metis_gateway.deps import BackendDep, OperatorDep
from metis_gateway.errors import ConflictError, ForbiddenError
from metis_gateway.schemas import AuthorizeView, ConnectionView
from metis_ingestion import OAuth2Client, OAuthTokens

router = APIRouter(prefix="/oauth", tags=["oauth"])

GoogleExchange = Callable[[str], Awaitable[OAuthTokens]]


def google_exchange(request: Request) -> GoogleExchange:
    """The code→tokens exchange used by the callback — overridable in tests via overrides.

    Builds an ``OAuth2Client`` per call over a short-lived HTTP client; raises if the flow is off.
    """
    config = request.app.state.backend.google_oauth
    if config is None:
        raise ConflictError("Google OAuth is not configured")

    async def exchange(code: str) -> OAuthTokens:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            oauth = OAuth2Client(
                token_url=config.token_url,
                client_id=config.client_id,
                client_secret=config.client_secret,
                http_client=client,
                redirect_uri=config.redirect_uri,
            )
            return await oauth.exchange_code(code)

    return exchange


ExchangeDep = Annotated[GoogleExchange, Depends(google_exchange)]


@router.get("/{connector}/authorize", response_model=AuthorizeView)
async def authorize(connector: str, backend: BackendDep, _principal: OperatorDep) -> AuthorizeView:
    if backend.google_oauth is None:
        raise ConflictError("Google OAuth is not configured")
    state = token_urlsafe(24)
    backend.oauth_states[state] = connector  # remember which connector this consent is for
    return AuthorizeView(authorize_url=backend.google_oauth.authorize_url(state=state), state=state)


@router.get("/callback", response_model=ConnectionView)
async def callback(
    code: str, state: str, backend: BackendDep, exchange: ExchangeDep, _principal: OperatorDep
) -> ConnectionView:
    connector = backend.oauth_states.pop(state, None)
    if connector is None:
        raise ForbiddenError("unknown or expired OAuth state")  # CSRF / replay guard
    if backend.credentials is None or backend.google_oauth is None:
        raise ConflictError("credential store or Google OAuth is not configured")
    tokens = await exchange(code)
    backend.credentials.set_credential(
        connector=connector, name="refresh_token", value=tokens.refresh_token
    )
    backend.credentials.set_credential(
        connector=connector, name="client_secret", value=backend.google_oauth.client_secret
    )
    return ConnectionView(connector=connector, status="connected")
