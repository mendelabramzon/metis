"""A live Google Drive ``Transport``: snapshot a folder over the Drive API, then serve from cache.

The connector spine (``base``) expects a synchronous ``Transport`` (``list_keys`` + ``read``) over a
fixed set of responses — exactly what ``RecordedTransport`` serves from fixtures and what
``GoogleDriveConnector`` reads as ``listing.json`` plus one content key per file. This is the live
sibling: on first access it lists the folder (following ``nextPageToken``, including shared drives),
*exports* Google-native Docs/Sheets to a parser-supported Office type and *downloads* other files,
and renders the ``listing.json`` the connector parses — caching everything so reads are byte-stable
and cursor replay holds. A file whose type no parser supports (an image, no OCR yet) is skipped.

The access token is already resolved (like ``ImapConfig`` holds a resolved password); the OAuth
refresh/expiry lifecycle is :mod:`metis_ingestion.connectors.oauth`, applied by the caller per sync.
The HTTP client is injected, so the suite drives the transport against a fake with no live Drive.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from metis_ingestion import mime
from metis_ingestion.connectors.base import ConnectorError
from metis_ingestion.parsers.registry import supported_media_types

_LISTING_KEY = "listing.json"

# Google-native types have no bytes to download — they must be exported to a concrete format.
_GOOGLE_EXPORTS = {
    "application/vnd.google-apps.document": mime.DOCX,
    "application/vnd.google-apps.spreadsheet": mime.XLSX,
}
_LIST_FIELDS = "nextPageToken,files(id,name,mimeType,modifiedTime,permissions(type,role))"


@dataclass(frozen=True)
class DriveConfig:
    """Which Drive folder to ingest, and the API root (overridable for a test/proxy endpoint)."""

    folder_id: str
    base_url: str = "https://www.googleapis.com/drive/v3"
    page_size: int = 100


@dataclass
class _Snapshot:
    listing: bytes
    content: dict[str, bytes] = field(default_factory=dict)


class DriveTransport:
    """A live Google Drive ``Transport`` — a folder snapshot, cached after the first access."""

    def __init__(self, config: DriveConfig, *, access_token: str, http_client: Any) -> None:
        self._config = config
        self._token = access_token
        self._http = http_client
        self._snapshot: _Snapshot | None = None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _list_files(self) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params = {
                "q": f"'{self._config.folder_id}' in parents and trashed=false",
                "fields": _LIST_FIELDS,
                "pageSize": str(self._config.page_size),
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page_token is not None:
                params["pageToken"] = page_token
            data = self._http.get(
                f"{self._config.base_url}/files", params=params, headers=self._headers()
            ).json()
            files.extend(data.get("files", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                return files

    def _content(self, drive_file: dict[str, Any]) -> tuple[str, bytes] | None:
        """The ``(media_type, bytes)`` for a file — export a Google doc, download a supported file,
        or ``None`` to skip a type no parser handles."""
        mime_type = drive_file.get("mimeType", "")
        file_id = drive_file["id"]
        export = _GOOGLE_EXPORTS.get(mime_type)
        if export is not None:
            url = f"{self._config.base_url}/files/{file_id}/export"
            data = self._http.get(url, params={"mimeType": export}, headers=self._headers()).content
            return export, data
        if mime_type in supported_media_types():
            url = f"{self._config.base_url}/files/{file_id}"
            params = {"alt": "media", "supportsAllDrives": "true"}
            return mime_type, self._http.get(url, params=params, headers=self._headers()).content
        return None

    def _load(self) -> _Snapshot:
        if self._snapshot is not None:
            return self._snapshot
        entries: list[dict[str, Any]] = []
        content: dict[str, bytes] = {}
        for drive_file in self._list_files():
            resolved = self._content(drive_file)
            if resolved is None:
                continue
            media_type, data = resolved
            file_id = drive_file["id"]
            content[file_id] = data
            entries.append(
                {
                    "id": file_id,
                    "name": drive_file.get("name", file_id),
                    "media_type": media_type,
                    "content_key": file_id,
                    "modified_time": drive_file.get("modifiedTime", ""),
                    "permissions": list(drive_file.get("permissions", [])),
                }
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
            raise ConnectorError(f"no Drive file {key!r}") from exc
