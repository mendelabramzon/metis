"""build_gmail_connector: resolve an access token from the stored refresh token, then build a
working Gmail connector over the live transport — the assembly the ingest worker calls per sync. The
OAuth token endpoint and the Gmail API are both faked, so there is no live Google."""

from __future__ import annotations

import base64
from typing import Any

from metis_ingestion import OAuth2Client, OAuthTokens, build_gmail_connector, mime
from metis_protocol import Sensitivity, WorkspaceId

_WS = WorkspaceId("ws_" + "a" * 32)
_MSG = b"From: ada@acme.com\nTo: team@acme.com\nSubject: Roadmap\n\nWe ship in 2026."


class _Resp:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeTokenHTTP:
    """The OAuth token endpoint: returns a fresh access token for a refresh exchange."""

    def __init__(self) -> None:
        self.calls = 0

    async def post(self, url: str, data: dict[str, str]) -> _Resp:
        self.calls += 1
        return _Resp({"access_token": "AT-google", "expires_in": 3600})


class _FakeGmailHTTP:
    """The Gmail API: serves one message list + its raw body; records the bearer it was sent."""

    def __init__(self) -> None:
        self.bearer: list[str | None] = []

    def get(self, url: str, params: dict[str, str], headers: dict[str, str]) -> _Resp:
        self.bearer.append(headers.get("Authorization"))
        if url.endswith("/messages"):
            return _Resp({"messages": [{"id": "m1"}]})
        raw = base64.urlsafe_b64encode(_MSG).decode().rstrip("=")
        return _Resp({"id": "m1", "internalDate": "1700000000001", "raw": raw})


async def test_resolves_a_token_and_builds_an_ingesting_connector() -> None:
    token_http = _FakeTokenHTTP()
    gmail_http = _FakeGmailHTTP()
    persisted: list[OAuthTokens] = []
    oauth = OAuth2Client(
        token_url="https://oauth.example/token",
        client_id="cid",
        client_secret="csecret",
        http_client=token_http,
    )

    connector = await build_gmail_connector(
        workspace_id=_WS,
        sensitivity=Sensitivity.CONFIDENTIAL,
        refresh_token="RT-durable",
        oauth=oauth,
        gmail_http=gmail_http,
        query="in:inbox",
        persist=persisted.append,
        base_url="https://gmail.example/v1",
    )

    refs = await connector.discover(None)
    assert [ref.locator for ref in refs] == ["m1"]
    raw, data = await connector.fetch_with_bytes(refs[0])
    assert data == _MSG  # ingested over the live transport with the resolved token
    assert raw.media_type == mime.EML

    assert token_http.calls == 1  # the refresh token was exchanged for an access token
    assert all(header == "Bearer AT-google" for header in gmail_http.bearer)
    assert len(persisted) == 1
    assert persisted[0].access_token == "AT-google"  # rotated token persisted back
