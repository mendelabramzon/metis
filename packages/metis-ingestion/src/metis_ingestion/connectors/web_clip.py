"""Web clipper / URL fetcher: capture a page's HTML as a web-page artifact (public by default).

A clipped page is just HTML the existing parser already turns into text, so this connector mostly
exists to stamp the right provenance and policy: web content defaults to ``PUBLIC`` (overridable for
an authenticated intranet clip). With no event timeline to track, the page key itself is the cursor,
so an incremental run picks up pages added since the last watermark; a re-clip of the same URL
dedups on content hash downstream.
"""

from __future__ import annotations

from collections.abc import Sequence

from metis_ingestion import mime
from metis_ingestion._build import stable_id
from metis_ingestion.connectors.base import BaseConnector, RateLimiter, RenderedPayload, Transport
from metis_ingestion.mime import MediaInfo
from metis_protocol import ArtifactKind, Sensitivity, SourceId, SourceRef, WorkspaceId

_PAGE_SUFFIXES = (".html", ".htm")


class WebClipConnector(BaseConnector):
    connector = "web_clip"

    def __init__(
        self,
        *,
        workspace_id: WorkspaceId,
        transport: Transport,
        sensitivity: Sensitivity = Sensitivity.PUBLIC,  # public unless told otherwise
        tags: Sequence[str] = (),
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__(
            workspace_id=workspace_id,
            transport=transport,
            sensitivity=sensitivity,
            tags=tags,
            rate_limiter=rate_limiter,
        )

    def _pages(self) -> list[str]:
        return [key for key in self._transport.list_keys() if key.endswith(_PAGE_SUFFIXES)]

    async def discover(self, cursor: str | None) -> Sequence[SourceRef]:
        refs: list[SourceRef] = []
        for key in self._pages():
            if cursor is not None and key <= cursor:
                continue
            refs.append(
                SourceRef(
                    source_id=stable_id(SourceId, f"web_clip:{key}"),
                    connector=self.connector,
                    locator=key,
                    cursor=key,
                )
            )
        return refs

    def _render(self, locator: str) -> RenderedPayload:
        return RenderedPayload(
            data=self._read(locator),
            media=MediaInfo(mime.HTML, ArtifactKind.WEB_PAGE),
            policy=self._policy(),
        )
