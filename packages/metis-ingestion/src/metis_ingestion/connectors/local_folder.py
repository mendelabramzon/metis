"""The local folder connector: recursive discovery + fetch/normalize of files on disk."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from metis_ingestion import mime
from metis_ingestion._build import stable_id
from metis_ingestion.normalize import build_normalized_doc
from metis_ingestion.raw import build_raw_artifact
from metis_protocol import (
    NormalizedDoc,
    PolicyState,
    RawArtifact,
    SourceId,
    SourceRef,
    WorkspaceId,
)

_HEAD_BYTES = 512


class LocalFolderConnector:
    def __init__(
        self,
        root: Path | str,
        *,
        workspace_id: WorkspaceId,
        policy: PolicyState | None = None,
    ) -> None:
        self._root = Path(root)
        self._workspace_id = workspace_id
        self._policy = policy if policy is not None else PolicyState()

    @property
    def workspace_id(self) -> WorkspaceId:
        return self._workspace_id

    async def discover(self, cursor: str | None) -> Sequence[SourceRef]:
        since = float(cursor) if cursor else None
        refs: list[SourceRef] = []
        for path in sorted(self._root.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            mtime = path.stat().st_mtime
            if since is not None and mtime <= since:
                continue
            locator = path.relative_to(self._root).as_posix()
            refs.append(
                SourceRef(
                    source_id=stable_id(SourceId, locator),
                    connector="local_folder",
                    locator=locator,
                    cursor=repr(mtime),
                )
            )
        return refs

    async def fetch_with_bytes(self, ref: SourceRef) -> tuple[RawArtifact, bytes]:
        data = (self._root / ref.locator).read_bytes()
        media = mime.detect(ref.locator, data[:_HEAD_BYTES])
        raw = build_raw_artifact(
            data,
            workspace_id=self._workspace_id,
            filename=ref.locator,
            media_info=media,
            policy=self._policy,
        )
        return raw, data

    async def fetch(self, ref: SourceRef) -> RawArtifact:
        raw, _ = await self.fetch_with_bytes(ref)
        return raw

    def normalize(self, raw: RawArtifact) -> NormalizedDoc:
        data = (self._root / (raw.filename or "")).read_bytes()
        return build_normalized_doc(raw, data, policy=self._policy)


if TYPE_CHECKING:
    from metis_protocol import Connector

    def _conforms(connector: LocalFolderConnector) -> Connector:
        return connector
