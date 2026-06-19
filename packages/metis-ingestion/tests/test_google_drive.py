"""build_google_drive_connector: resolve an access token from the stored refresh token, then build
a working Drive connector over the live transport — the assembly the ingest worker calls per sync.
The OAuth token endpoint and the Drive API are both faked, so there is no live Google."""

from __future__ import annotations

from typing import Any

from metis_ingestion import OAuth2Client, OAuthTokens, build_google_drive_connector, mime
from metis_protocol import Sensitivity, WorkspaceId

_WS = WorkspaceId("ws_" + "a" * 32)
_PDF = {
    "id": "pdf1",
    "name": "report.pdf",
    "mimeType": mime.PDF,
    "modifiedTime": "2026-01-03T10:00:00Z",
    "permissions": [{"type": "anyone", "role": "reader"}],
}


class _Resp:
    def __init__(self, *, payload: dict[str, Any] | None = None, content: bytes = b"") -> None:
        self._payload = payload
        self.content = content

    def json(self) -> dict[str, Any]:
        assert self._payload is not None
        return self._payload


class _FakeTokenHTTP:
    """The OAuth token endpoint: returns a fresh access token for a refresh exchange."""

    def __init__(self) -> None:
        self.calls = 0

    async def post(self, url: str, data: dict[str, str]) -> _Resp:
        self.calls += 1
        return _Resp(payload={"access_token": "AT-google", "expires_in": 3600})


class _FakeDriveHTTP:
    """The Drive API: serves one file listing + its content; records the bearer it was sent."""

    def __init__(self) -> None:
        self.bearer: list[str | None] = []

    def get(self, url: str, params: dict[str, str], headers: dict[str, str]) -> _Resp:
        self.bearer.append(headers.get("Authorization"))
        if url.endswith("/files"):
            return _Resp(payload={"files": [_PDF]})
        return _Resp(content=b"%PDF-bytes")


async def test_resolves_a_token_and_builds_an_ingesting_connector() -> None:
    token_http = _FakeTokenHTTP()
    drive_http = _FakeDriveHTTP()
    persisted: list[OAuthTokens] = []
    oauth = OAuth2Client(
        token_url="https://oauth.example/token",
        client_id="cid",
        client_secret="csecret",
        http_client=token_http,
    )

    connector = await build_google_drive_connector(
        workspace_id=_WS,
        folder_id="folderX",
        sensitivity=Sensitivity.INTERNAL,
        refresh_token="RT-durable",
        oauth=oauth,
        drive_http=drive_http,
        persist=persisted.append,
        base_url="https://drive.example/v3",
    )

    refs = await connector.discover(None)
    assert [ref.locator for ref in refs] == ["pdf1"]
    _, data = await connector.fetch_with_bytes(refs[0])
    assert data == b"%PDF-bytes"  # ingested over the live transport with the resolved token

    assert token_http.calls == 1  # the refresh token was exchanged for an access token
    assert all(header == "Bearer AT-google" for header in drive_http.bearer)
    assert len(persisted) == 1
    assert persisted[0].access_token == "AT-google"  # rotated token persisted back
