"""OAuth token lifecycle: authorization-code exchange and refresh against a fake token endpoint, and
a RefreshingTokenProvider that refreshes only when the access token is expiring and persists the
result — the refresh/expiry seam a live Google connector sits on (no live provider in the suite)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from metis_ingestion.connectors import (
    OAuth2Client,
    OAuthTokens,
    RefreshingTokenProvider,
)
from metis_ingestion.connectors.base import AuthError


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeTokenEndpoint:
    """Records token requests and replays canned payloads (the last repeats)."""

    def __init__(self, payloads: Sequence[dict[str, Any]]) -> None:
        self._payloads = list(payloads)
        self.calls: list[dict[str, str]] = []

    async def post(self, url: str, data: dict[str, str]) -> _FakeResponse:
        self.calls.append(data)
        index = min(len(self.calls) - 1, len(self._payloads) - 1)
        return _FakeResponse(self._payloads[index])


def _client(endpoint: _FakeTokenEndpoint, **overrides: Any) -> OAuth2Client:
    kwargs: dict[str, Any] = {
        "token_url": "https://oauth.example/token",
        "client_id": "cid",
        "client_secret": "csecret",
        "http_client": endpoint,
        "redirect_uri": "https://app.example/oauth/callback",
    }
    kwargs.update(overrides)
    return OAuth2Client(**kwargs)


async def test_exchange_code_returns_and_requests_tokens() -> None:
    endpoint = _FakeTokenEndpoint(
        [{"access_token": "AT1", "refresh_token": "RT1", "expires_in": 3600}]
    )
    tokens = await _client(endpoint).exchange_code("auth-code-123")

    assert tokens.access_token == "AT1"
    assert tokens.refresh_token == "RT1"
    sent = endpoint.calls[0]
    assert sent["grant_type"] == "authorization_code"
    assert sent["code"] == "auth-code-123"
    assert sent["client_id"] == "cid"
    assert sent["client_secret"] == "csecret"
    assert sent["redirect_uri"] == "https://app.example/oauth/callback"


async def test_refresh_keeps_the_prior_refresh_token_when_omitted() -> None:
    # Google omits refresh_token on a refresh response; we must keep the one we sent.
    endpoint = _FakeTokenEndpoint([{"access_token": "AT2", "expires_in": 3600}])
    tokens = await _client(endpoint).refresh("RT-durable")

    assert tokens.access_token == "AT2"
    assert tokens.refresh_token == "RT-durable"
    assert endpoint.calls[0]["grant_type"] == "refresh_token"


async def test_provider_refreshes_when_expiring_then_caches() -> None:
    endpoint = _FakeTokenEndpoint([{"access_token": "fresh-AT", "expires_in": 3600}])
    persisted: list[OAuthTokens] = []
    provider = RefreshingTokenProvider.from_refresh_token(
        oauth=_client(endpoint), refresh_token="RT-durable", persist=persisted.append
    )

    first = await provider.access_token()
    second = await provider.access_token()

    assert first == "fresh-AT"
    assert second == "fresh-AT"
    assert len(endpoint.calls) == 1  # refreshed once; the second call used the cached token
    assert len(persisted) == 1
    assert persisted[0].access_token == "fresh-AT"


async def test_provider_returns_a_still_fresh_token_without_a_network_call() -> None:
    endpoint = _FakeTokenEndpoint([{"access_token": "unused", "expires_in": 3600}])
    fresh = OAuthTokens(
        access_token="cached-AT",
        refresh_token="RT",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    provider = RefreshingTokenProvider(oauth=_client(endpoint), tokens=fresh)

    assert await provider.access_token() == "cached-AT"
    assert endpoint.calls == []  # nothing was within the expiry skew, so no refresh happened


async def test_token_endpoint_error_raises_auth_error() -> None:
    endpoint = _FakeTokenEndpoint([{"error": "invalid_grant"}])
    with pytest.raises(AuthError, match="invalid_grant"):
        await _client(endpoint).refresh("RT-bad")
