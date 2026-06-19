"""The Google OAuth consent flow: authorize returns a consent URL + CSRF state; the callback
exchanges the code (faked) and writes the refresh token into the encrypted credential store under
the connector — what the ingest worker resolves. The CSRF state is enforced and single-use, and the
flow is operator-only; when no client is configured it is disabled."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from metis_core.security import generate_key
from metis_gateway.app import create_app
from metis_gateway.routers.oauth import google_exchange
from metis_gateway.settings import GatewaySettings
from metis_ingestion import OAuthTokens

_OP = {"Authorization": "Bearer op-token"}
_USER = {"Authorization": "Bearer user-token"}
_TOKENS = OAuthTokens(
    access_token="AT", refresh_token="RT-google", expires_at=datetime.now(UTC) + timedelta(hours=1)
)


def _google_settings() -> GatewaySettings:
    return GatewaySettings(
        operator_token="op-token",
        user_token="user-token",
        workspace_id="ws_" + "1" * 32,
        google_client_id="client-123",
        google_client_secret="secret-xyz",
        google_redirect_uri="https://app.example/oauth/callback",
        cred_store_key=generate_key(),
    )


@pytest.fixture
def google_app() -> Iterator[tuple[FastAPI, TestClient]]:
    app = create_app(_google_settings())

    async def _fake_exchange(code: str) -> OAuthTokens:
        assert code == "auth-code-1"
        return _TOKENS

    app.dependency_overrides[google_exchange] = lambda: _fake_exchange
    with TestClient(app) as client:
        yield app, client


def test_authorize_then_callback_stores_the_refresh_token(google_app) -> None:
    app, client = google_app

    authz = client.get("/oauth/gdrive/authorize", headers=_OP)
    assert authz.status_code == 200, authz.text
    body = authz.json()
    assert "client_id=client-123" in body["authorize_url"]
    assert "access_type=offline" in body["authorize_url"]  # ask Google for a refresh token
    state = body["state"]

    cb = client.get(f"/oauth/callback?code=auth-code-1&state={state}", headers=_OP)
    assert cb.status_code == 200, cb.text
    assert cb.json() == {"connector": "gdrive", "status": "connected"}

    # The refresh token + client secret landed in the encrypted store under the gdrive namespace.
    resolver = app.state.backend.credentials.for_connector("gdrive")
    assert resolver.resolve("refresh_token") == "RT-google"
    assert resolver.resolve("client_secret") == "secret-xyz"


def test_callback_rejects_an_unknown_state(google_app) -> None:
    _, client = google_app
    cb = client.get("/oauth/callback?code=auth-code-1&state=forged", headers=_OP)
    assert cb.status_code == 403  # CSRF / replay guard


def test_state_is_single_use(google_app) -> None:
    _, client = google_app
    state = client.get("/oauth/gdrive/authorize", headers=_OP).json()["state"]
    first = client.get(f"/oauth/callback?code=auth-code-1&state={state}", headers=_OP)
    assert first.status_code == 200
    replay = client.get(f"/oauth/callback?code=auth-code-1&state={state}", headers=_OP)
    assert replay.status_code == 403  # the state was consumed


def test_flow_is_operator_only(google_app) -> None:
    _, client = google_app
    assert client.get("/oauth/gdrive/authorize", headers=_USER).status_code == 403


def test_flow_disabled_without_a_client(client, op) -> None:
    # The default app configures no Google client, so the flow is off.
    assert client.get("/oauth/gdrive/authorize", headers=op).status_code == 409
