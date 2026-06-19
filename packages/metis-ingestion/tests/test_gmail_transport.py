"""The live Gmail Transport maps the Gmail API onto what GmailConnector reads: a listing.json plus
one content key per message. Messages are listed (with pagination), fetched in format=raw, the
base64url RFC822 is decoded, and the token is sent — all against a fake with no live Gmail."""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from metis_ingestion import GmailConfig, GmailConnector, GmailTransport, mime
from metis_ingestion.connectors.base import ConnectorError
from metis_protocol import WorkspaceId

_WS = WorkspaceId("ws_" + "a" * 32)
_MESSAGES = {
    "m1": b"From: ada@acme.com\nTo: team@acme.com\nSubject: Roadmap\n\nWe ship in 2026.",
    "m2": b"From: grace@acme.com\nTo: team@acme.com\nSubject: Hello\n\nGrace here.",
}
_DATES = {"m1": "1700000000001", "m2": "1700000000002"}


def _raw(data: bytes) -> str:
    """Gmail returns format=raw as unpadded base64url."""
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


class _Resp:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeGmail:
    """Serves a paged message list and per-message raw bodies; records the bearers it was sent."""

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages
        self.bearer: list[str | None] = []

    def get(self, url: str, params: dict[str, str], headers: dict[str, str]) -> _Resp:
        self.bearer.append(headers.get("Authorization"))
        if url.endswith("/messages"):
            return _Resp(self._pages[int(params.get("pageToken", "0"))])
        message_id = url.rsplit("/", 1)[1]
        return _Resp(
            {
                "id": message_id,
                "internalDate": _DATES[message_id],
                "raw": _raw(_MESSAGES[message_id]),
            }
        )


def _transport(pages: list[dict[str, Any]], *, token: str = "AT") -> GmailTransport:
    return GmailTransport(GmailConfig(), access_token=token, http_client=_FakeGmail(pages))


def test_lists_messages_and_decodes_raw() -> None:
    transport = _transport([{"messages": [{"id": "m1"}, {"id": "m2"}]}])

    listing = {entry["id"]: entry for entry in json.loads(transport.read("listing.json"))}
    assert set(listing) == {"m1", "m2"}
    assert listing["m1"]["internal_date"] == "1700000000001"
    assert transport.read("m1") == _MESSAGES["m1"]  # the base64url RFC822 was decoded
    assert list(transport.list_keys()) == ["listing.json", "m1", "m2"]


def test_sends_the_access_token_as_a_bearer() -> None:
    client = _FakeGmail([{"messages": [{"id": "m1"}]}])
    GmailTransport(GmailConfig(), access_token="secret-token", http_client=client).read(
        "listing.json"
    )
    assert client.bearer  # the list + fetch calls happened
    assert all(header == "Bearer secret-token" for header in client.bearer)


def test_follows_pagination() -> None:
    pages = [
        {"messages": [{"id": "m1"}], "nextPageToken": "1"},
        {"messages": [{"id": "m2"}]},
    ]
    listing = {entry["id"] for entry in json.loads(_transport(pages).read("listing.json"))}
    assert listing == {"m1", "m2"}  # both pages were ingested


def test_unknown_key_raises() -> None:
    transport = _transport([{"messages": [{"id": "m1"}]}])
    with pytest.raises(ConnectorError, match="missing"):
        transport.read("missing")


async def test_connector_ingests_over_the_live_transport() -> None:
    connector = GmailConnector(
        workspace_id=_WS, transport=_transport([{"messages": [{"id": "m1"}, {"id": "m2"}]}])
    )

    refs = await connector.discover(None)
    assert {ref.locator for ref in refs} == {"m1", "m2"}

    raw, data = await connector.fetch_with_bytes(refs[0])
    assert data in _MESSAGES.values()  # the RFC822 bytes, fetched via the transport
    assert raw.media_type == mime.EML  # ingested as an email the .eml parser reads


async def test_discover_is_incremental_by_internal_date() -> None:
    connector = GmailConnector(
        workspace_id=_WS, transport=_transport([{"messages": [{"id": "m1"}, {"id": "m2"}]}])
    )
    refs = await connector.discover("1700000000001")  # only mail newer than m1's date
    assert [ref.locator for ref in refs] == ["m2"]
