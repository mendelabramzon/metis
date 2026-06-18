"""Every connector emits a valid ``RawArtifact`` + ``NormalizedDoc`` — the cross-source invariant.

Whatever a source looks like on the wire, downstream stages only ever see the same two artifacts, so
this is the contract that keeps connector-specific shapes from leaking past normalization.
"""

import pytest

from metis_ingestion import get_format
from metis_ingestion.connectors import ConnectorRegistry, RecordedTransport
from metis_protocol import NormalizedDoc, RawArtifact

CONNECTORS = ["imap", "slack", "web_clip", "gdrive", "calendar"]


@pytest.mark.parametrize("name", CONNECTORS)
async def test_connector_emits_valid_raw_and_normalized(name, connectors_root, workspace) -> None:
    registry = ConnectorRegistry.with_defaults()
    connector = registry.create(
        name, workspace_id=workspace, transport=RecordedTransport(connectors_root / name)
    )

    refs = await connector.discover(None)
    assert refs, f"{name} discovered nothing"

    for ref in refs:
        raw, data = await connector.fetch_with_bytes(ref)
        assert isinstance(raw, RawArtifact)
        assert raw.content_hash
        assert raw.byte_size == len(data)
        assert raw.storage_ref  # content-addressed object key
        assert raw.provenance.attribution.agent == name  # provenance names the producing connector
        assert get_format(raw.media_type) is not None  # a media type the pipeline can parse

        doc = connector.normalize(raw)
        assert isinstance(doc, NormalizedDoc)
        assert doc.artifact_id == raw.id  # the doc points back at its raw artifact
        assert doc.media_type == raw.media_type
        assert doc.text.strip()  # non-empty normalized text
