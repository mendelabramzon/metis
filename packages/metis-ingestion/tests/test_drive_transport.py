"""The live Drive Transport maps the Drive API onto what GoogleDriveConnector reads: a listing.json
plus one content key per file. Google docs are exported to an Office type, other supported files are
downloaded, unsupported types are skipped, pages are followed, and the access token is sent — all
against a fake HTTP client with no live Drive."""

from __future__ import annotations

import json
from typing import Any

import pytest

from metis_ingestion import DriveConfig, DriveTransport, GoogleDriveConnector, mime
from metis_ingestion.connectors.base import ConnectorError
from metis_protocol import WorkspaceId

_WS = WorkspaceId("ws_" + "a" * 32)
_DOC = {
    "id": "doc1",
    "name": "Roadmap",
    "mimeType": "application/vnd.google-apps.document",
    "modifiedTime": "2026-01-02T10:00:00Z",
    "permissions": [{"type": "domain", "role": "reader"}],
}
_PDF = {
    "id": "pdf1",
    "name": "report.pdf",
    "mimeType": mime.PDF,
    "modifiedTime": "2026-01-03T10:00:00Z",
    "permissions": [{"type": "anyone", "role": "reader"}],
}
_IMAGE = {"id": "img1", "name": "logo.png", "mimeType": "image/png", "modifiedTime": "2026-01-01"}
_CONTENT = {"doc1": b"exported-docx-bytes", "pdf1": b"%PDF-fake-bytes"}


class _Resp:
    def __init__(self, *, payload: dict[str, Any] | None = None, content: bytes = b"") -> None:
        self._payload = payload
        self.content = content

    def json(self) -> dict[str, Any]:
        assert self._payload is not None
        return self._payload


class _FakeDrive:
    """Serves a paged file listing and per-file content; records the bearer tokens it was sent."""

    def __init__(self, pages: list[dict[str, Any]], content: dict[str, bytes]) -> None:
        self._pages = pages
        self._content = content
        self.bearer: list[str | None] = []

    def get(self, url: str, params: dict[str, str], headers: dict[str, str]) -> _Resp:
        self.bearer.append(headers.get("Authorization"))
        if url.endswith("/files"):
            index = int(params.get("pageToken", "0"))
            return _Resp(payload=self._pages[index])
        if "/export" in url:
            file_id = url.split("/files/", 1)[1].split("/export", 1)[0]
            return _Resp(content=self._content[file_id])
        file_id = url.rsplit("/", 1)[1]
        return _Resp(content=self._content[file_id])


def _transport(pages: list[dict[str, Any]], *, token: str = "AT") -> DriveTransport:
    return DriveTransport(
        DriveConfig(folder_id="folderX"),
        access_token=token,
        http_client=_FakeDrive(pages, _CONTENT),
    )


def test_exports_docs_downloads_files_and_skips_unsupported() -> None:
    transport = _transport([{"files": [_DOC, _PDF, _IMAGE]}])

    listing = {entry["id"]: entry for entry in json.loads(transport.read("listing.json"))}
    assert set(listing) == {"doc1", "pdf1"}  # the image (no parser) was skipped
    assert listing["doc1"]["media_type"] == mime.DOCX  # Google doc exported to docx
    assert listing["pdf1"]["media_type"] == mime.PDF  # native file downloaded as-is
    assert listing["doc1"]["permissions"] == [{"type": "domain", "role": "reader"}]
    assert transport.read("doc1") == b"exported-docx-bytes"
    assert transport.read("pdf1") == b"%PDF-fake-bytes"
    assert list(transport.list_keys()) == ["listing.json", "doc1", "pdf1"]


def test_sends_the_access_token_as_a_bearer() -> None:
    client = _FakeDrive([{"files": [_PDF]}], _CONTENT)
    transport = DriveTransport(
        DriveConfig(folder_id="folderX"), access_token="secret-token", http_client=client
    )
    transport.read("listing.json")
    assert client.bearer  # at least the list + download calls happened
    assert all(header == "Bearer secret-token" for header in client.bearer)


def test_follows_pagination() -> None:
    pages = [
        {"files": [_DOC], "nextPageToken": "1"},
        {"files": [_PDF]},
    ]
    transport = _transport(pages)
    listing = {entry["id"] for entry in json.loads(transport.read("listing.json"))}
    assert listing == {"doc1", "pdf1"}  # both pages were ingested


def test_unknown_key_raises() -> None:
    transport = _transport([{"files": [_PDF]}])
    with pytest.raises(ConnectorError, match="missing"):
        transport.read("missing")


async def test_connector_ingests_over_the_live_transport() -> None:
    connector = GoogleDriveConnector(
        workspace_id=_WS, transport=_transport([{"files": [_DOC, _PDF]}])
    )

    refs = await connector.discover(None)
    assert {ref.locator for ref in refs} == {"doc1", "pdf1"}

    pdf_ref = next(ref for ref in refs if ref.locator == "pdf1")
    _, data = await connector.fetch_with_bytes(pdf_ref)
    assert (
        data == b"%PDF-fake-bytes"
    )  # the connector fetched the downloaded bytes via the transport
