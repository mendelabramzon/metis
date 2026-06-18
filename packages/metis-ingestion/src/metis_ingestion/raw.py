"""Build content-addressed RawArtifacts (the immutable evidence-truth record)."""

from __future__ import annotations

import hashlib

from metis_core.objectstore import content_key
from metis_ingestion._build import make_provenance, now_utc, stable_id
from metis_ingestion.mime import MediaInfo
from metis_protocol import AgentKind, ArtifactId, PolicyState, RawArtifact, WorkspaceId


def build_raw_artifact(
    data: bytes,
    *,
    workspace_id: WorkspaceId,
    filename: str,
    media_info: MediaInfo,
    policy: PolicyState,
    connector: str = "local_folder",
    trace_id: str | None = None,
) -> RawArtifact:
    """Build a ``RawArtifact``; ``storage_ref`` is the content-addressed object key.

    ``connector`` names the producing connector in provenance (the PROV agent), so an artifact
    is traceable to the source that fetched it regardless of which connector that was.
    """
    content_hash = hashlib.sha256(data).hexdigest()
    return RawArtifact(
        id=stable_id(ArtifactId, f"{workspace_id}:{content_hash}"),
        provenance=make_provenance(
            workspace_id, agent_kind=AgentKind.CONNECTOR, agent=connector, trace_id=trace_id
        ),
        policy=policy,
        created_at=now_utc(),
        kind=media_info.kind,
        content_hash=content_hash,
        media_type=media_info.media_type,
        byte_size=len(data),
        storage_ref=content_key(data),
        filename=filename,
    )
