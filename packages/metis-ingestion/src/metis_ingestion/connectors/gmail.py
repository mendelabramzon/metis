"""Gmail connector: ingest messages from the Gmail API as RFC822 (the .eml parser reads them).

Gmail's ``format=raw`` returns the full RFC822 message — the same bytes a .eml file holds — so each
message becomes an email artifact the existing EML parser extracts (headers, body, attachments). The
message's ``internalDate`` is its cursor, so an incremental sync re-ingests only newer mail. Mailbox
messages carry the source's sensitivity (there is no per-message ACL, unlike Drive's shared files).
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, TypeAdapter

from metis_ingestion._build import stable_id
from metis_ingestion.connectors.base import BaseConnector, ConnectorError, RenderedPayload
from metis_ingestion.mime import EML, MediaInfo
from metis_protocol import ArtifactKind, SourceId, SourceRef

_LISTING_KEY = "listing.json"


class _GmailMessage(BaseModel):
    id: str
    content_key: str  # transport key holding the raw RFC822 bytes
    internal_date: str  # Gmail internalDate (ms since epoch); the incremental-sync cursor


_LISTING = TypeAdapter(tuple[_GmailMessage, ...])


class GmailConnector(BaseConnector):
    connector = "gmail"

    def _messages(self) -> tuple[_GmailMessage, ...]:
        return _LISTING.validate_json(self._read(_LISTING_KEY))

    async def discover(self, cursor: str | None) -> Sequence[SourceRef]:
        refs: list[SourceRef] = []
        for message in self._messages():
            if cursor is not None and message.internal_date <= cursor:
                continue
            refs.append(
                SourceRef(
                    source_id=stable_id(SourceId, f"gmail:{message.id}"),
                    connector=self.connector,
                    locator=message.id,
                    cursor=message.internal_date,
                )
            )
        return refs

    def _render(self, locator: str) -> RenderedPayload:
        for message in self._messages():
            if message.id == locator:
                return RenderedPayload(
                    data=self._read(message.content_key),
                    media=MediaInfo(EML, ArtifactKind.EMAIL),
                    policy=self._policy(self._sensitivity),
                )
        raise ConnectorError(f"unknown gmail message {locator!r}")
