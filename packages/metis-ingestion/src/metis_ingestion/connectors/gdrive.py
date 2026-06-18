"""Google Drive connector: ingest listed files, mapping Drive permissions to sensitivity.

Drive's ACL is the sensitivity signal: a file shared with "anyone" is public, one shared to the
whole domain is internal, and one restricted to named users is confidential — and that mapping must
ride into the artifact's policy, never the file's default. Each listed file becomes a doc from its
exported content; the file's ``modified_time`` is its cursor, so an incremental sync re-ingests only
what changed.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, TypeAdapter

from metis_ingestion._build import stable_id
from metis_ingestion.connectors.base import BaseConnector, ConnectorError, RenderedPayload
from metis_ingestion.mime import MediaInfo
from metis_protocol import ArtifactKind, Sensitivity, SourceId, SourceRef, max_sensitivity

_LISTING_KEY = "listing.json"


class _Permission(BaseModel):
    type: str  # "anyone" | "domain" | "user"
    role: str = "reader"


class _DriveFile(BaseModel):
    id: str
    name: str
    media_type: str  # the exported/native media type (a parser-supported type)
    content_key: str  # transport key holding the exported content bytes
    modified_time: str
    permissions: tuple[_Permission, ...] = ()

    @property
    def acl_floor(self) -> Sensitivity:
        types = {permission.type for permission in self.permissions}
        if "anyone" in types:
            return Sensitivity.PUBLIC
        if "domain" in types:
            return Sensitivity.INTERNAL
        return Sensitivity.CONFIDENTIAL  # shared only with named users


_LISTING = TypeAdapter(tuple[_DriveFile, ...])


class GoogleDriveConnector(BaseConnector):
    connector = "gdrive"

    def _files(self) -> tuple[_DriveFile, ...]:
        return _LISTING.validate_json(self._read(_LISTING_KEY))

    async def discover(self, cursor: str | None) -> Sequence[SourceRef]:
        refs: list[SourceRef] = []
        for drive_file in self._files():
            if cursor is not None and drive_file.modified_time <= cursor:
                continue
            refs.append(
                SourceRef(
                    source_id=stable_id(SourceId, f"gdrive:{drive_file.id}"),
                    connector=self.connector,
                    locator=drive_file.id,
                    cursor=drive_file.modified_time,
                )
            )
        return refs

    def _render(self, locator: str) -> RenderedPayload:
        for drive_file in self._files():
            if drive_file.id == locator:
                return RenderedPayload(
                    data=self._read(drive_file.content_key),
                    media=MediaInfo(drive_file.media_type, ArtifactKind.FILE),
                    policy=self._policy(max_sensitivity(self._sensitivity, drive_file.acl_floor)),
                )
        raise ConnectorError(f"unknown drive file {locator!r}")
