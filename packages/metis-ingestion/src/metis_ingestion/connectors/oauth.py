"""OAuth 2.0 token lifecycle for connectors — the refresh/expiry half of the ``oauth2()`` auth seam.

A connector's durable secret is its *refresh token* (named by :func:`oauth2`, held in the encrypted
credential store); the access token is short-lived and derived. ``RefreshingTokenProvider`` hands a
transport a currently-valid access token, exchanging the refresh token for a new one at the
provider's token endpoint when the access token nears expiry, and persisting any rotated refresh
token back. The one-time authorization-code exchange (at consent time) lives here too. Both the
exchange and the refresh go through an injected async HTTP client, so the suite drives them against
a fake token endpoint with no live provider.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from metis_ingestion.connectors.base import AuthError

_EXPIRY_SKEW = timedelta(seconds=60)
_DEFAULT_EXPIRES_IN = 3600


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class OAuthTokens:
    """A short-lived access token, the durable refresh token, and when the access token expires."""

    access_token: str
    refresh_token: str
    expires_at: datetime

    def is_fresh(self, *, now: datetime, skew: timedelta = _EXPIRY_SKEW) -> bool:
        """Whether the access token is present and not yet within ``skew`` of expiring."""
        return bool(self.access_token) and now < self.expires_at - skew


@runtime_checkable
class TokenProvider(Protocol):
    """Hands a transport a currently-valid access token, refreshing transparently as needed."""

    async def access_token(self) -> str: ...


class OAuth2Client:
    """Exchanges authorization codes and refresh tokens for access tokens at a token endpoint."""

    def __init__(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        http_client: Any,
        redirect_uri: str | None = None,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http_client
        self._redirect_uri = redirect_uri

    async def exchange_code(self, code: str) -> OAuthTokens:
        """Trade a one-time authorization code (from the consent redirect) for the first tokens."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        if self._redirect_uri is not None:
            data["redirect_uri"] = self._redirect_uri
        return await self._post(data, prior_refresh=None)

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        """Trade the durable refresh token for a fresh access token (keeping the refresh token)."""
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        return await self._post(data, prior_refresh=refresh_token)

    async def _post(self, data: dict[str, str], *, prior_refresh: str | None) -> OAuthTokens:
        response = await self._http.post(self._token_url, data=data)
        payload = response.json()
        if not isinstance(payload, dict) or "access_token" not in payload:
            error = payload.get("error") if isinstance(payload, dict) else payload
            raise AuthError(f"OAuth token endpoint returned no access_token: {error}")
        # Google omits refresh_token on a refresh response — keep the one we sent.
        refresh = str(payload.get("refresh_token") or prior_refresh or "")
        if not refresh:
            raise AuthError("OAuth response carried no refresh_token and none was supplied")
        expires_in = int(payload.get("expires_in", _DEFAULT_EXPIRES_IN))
        return OAuthTokens(
            access_token=str(payload["access_token"]),
            refresh_token=refresh,
            expires_at=_utcnow() + timedelta(seconds=expires_in),
        )


class RefreshingTokenProvider:
    """A ``TokenProvider`` that refreshes (and persists) the access token when it is expiring."""

    def __init__(
        self,
        *,
        oauth: OAuth2Client,
        tokens: OAuthTokens,
        persist: Callable[[OAuthTokens], None] | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._oauth = oauth
        self._tokens = tokens
        self._persist = persist
        self._clock = clock

    @classmethod
    def from_refresh_token(
        cls,
        *,
        oauth: OAuth2Client,
        refresh_token: str,
        persist: Callable[[OAuthTokens], None] | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> RefreshingTokenProvider:
        """Seed from only a stored refresh token; the epoch expiry forces a refresh on first use."""
        seed = OAuthTokens(
            access_token="",
            refresh_token=refresh_token,
            expires_at=datetime.fromtimestamp(0, tz=UTC),
        )
        return cls(oauth=oauth, tokens=seed, persist=persist, clock=clock)

    @property
    def tokens(self) -> OAuthTokens:
        return self._tokens

    async def access_token(self) -> str:
        if not self._tokens.is_fresh(now=self._clock()):
            self._tokens = await self._oauth.refresh(self._tokens.refresh_token)
            if self._persist is not None:
                self._persist(self._tokens)
        return self._tokens.access_token
