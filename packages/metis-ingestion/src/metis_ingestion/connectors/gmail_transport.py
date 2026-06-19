"""A live Gmail ``Transport``: snapshot a mailbox over the Gmail API, then serve from cache.

Mirrors the Drive transport: the connector spine (``base``) expects a synchronous ``Transport``
(``list_keys`` + ``read``) over a fixed set of responses — here a ``listing.json`` plus one content
key per message. On first access it lists messages (following ``nextPageToken``, optionally filtered
by a Gmail search query and label ids), fetches each in ``format=raw`` (the base64url RFC822 a .eml
holds), and renders the listing — caching everything so reads are byte-stable and replay is stable.

The access token is already resolved (like ``ImapConfig`` holds a resolved password); the OAuth
refresh/expiry lifecycle is :mod:`metis_ingestion.connectors.oauth`, applied by the caller per sync.
The HTTP client is injected, so the suite drives the transport against a fake with no live Gmail.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from metis_ingestion.connectors.base import ConnectorError

_LISTING_KEY = "listing.json"


@dataclass(frozen=True)
class GmailConfig:
    """Which mailbox slice to ingest: a Gmail search query + label ids, and the API root."""

    user_id: str = "me"
    query: str = ""
    label_ids: tuple[str, ...] = ()
    base_url: str = "https://gmail.googleapis.com/gmail/v1"
    page_size: int = 100


@dataclass
class _Snapshot:
    listing: bytes
    content: dict[str, bytes] = field(default_factory=dict)


def _decode_raw(raw: str) -> bytes:
    """Gmail's ``format=raw`` body is base64url (often unpadded) RFC822."""
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


class GmailTransport:
    """A live Gmail ``Transport`` — a mailbox snapshot, cached after the first access."""

    def __init__(self, config: GmailConfig, *, access_token: str, http_client: Any) -> None:
        self._config = config
        self._token = access_token
        self._http = http_client
        self._snapshot: _Snapshot | None = None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _messages_url(self, suffix: str = "") -> str:
        return f"{self._config.base_url}/users/{self._config.user_id}/messages{suffix}"

    def _list_message_ids(self) -> list[str]:
        ids: list[str] = []
        page_token: str | None = None
        while True:
            params: dict[str, str] = {"maxResults": str(self._config.page_size)}
            if self._config.query:
                params["q"] = self._config.query
            if self._config.label_ids:
                params["labelIds"] = ",".join(self._config.label_ids)
            if page_token is not None:
                params["pageToken"] = page_token
            data = self._http.get(
                self._messages_url(), params=params, headers=self._headers()
            ).json()
            ids.extend(message["id"] for message in data.get("messages", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                return ids

    def _fetch(self, message_id: str) -> tuple[bytes, str]:
        """The ``(rfc822_bytes, internal_date)`` for one message, fetched in ``format=raw``."""
        data = self._http.get(
            self._messages_url(f"/{message_id}"),
            params={"format": "raw"},
            headers=self._headers(),
        ).json()
        return _decode_raw(data["raw"]), str(data.get("internalDate", ""))

    def _load(self) -> _Snapshot:
        if self._snapshot is not None:
            return self._snapshot
        entries: list[dict[str, Any]] = []
        content: dict[str, bytes] = {}
        for message_id in self._list_message_ids():
            rfc822, internal_date = self._fetch(message_id)
            content[message_id] = rfc822
            entries.append(
                {"id": message_id, "content_key": message_id, "internal_date": internal_date}
            )
        self._snapshot = _Snapshot(listing=json.dumps(entries).encode("utf-8"), content=content)
        return self._snapshot

    def list_keys(self, prefix: str = "") -> Sequence[str]:
        snapshot = self._load()
        keys = [_LISTING_KEY, *sorted(snapshot.content)]
        return [k for k in keys if k.startswith(prefix)] if prefix else keys

    def read(self, key: str) -> bytes:
        snapshot = self._load()
        if key == _LISTING_KEY:
            return snapshot.listing
        try:
            return snapshot.content[key]
        except KeyError as exc:
            raise ConnectorError(f"no Gmail message {key!r}") from exc
