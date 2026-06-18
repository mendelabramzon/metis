"""Cursor replay is deterministic: re-discovery is identical and a watermark yields only newer work.

Incremental sync rests on this — the same recorded source produces the same refs and the same
content-addressed ids every run, and discovering past the latest cursor returns nothing.
"""

import pytest

from metis_ingestion.connectors import ConnectorRegistry, RecordedTransport

CONNECTORS = ["imap", "slack", "web_clip", "gdrive", "calendar"]


def _make(name, connectors_root, workspace):
    return ConnectorRegistry.with_defaults().create(
        name, workspace_id=workspace, transport=RecordedTransport(connectors_root / name)
    )


@pytest.mark.parametrize("name", CONNECTORS)
async def test_discovery_is_stable_and_watermark_excludes_seen(
    name, connectors_root, workspace
) -> None:
    connector = _make(name, connectors_root, workspace)

    first = await connector.discover(None)
    second = await connector.discover(None)
    # Re-discovery is byte-for-byte identical (stable ids, locators, cursors).
    assert [(r.source_id, r.locator, r.cursor) for r in first] == [
        (r.source_id, r.locator, r.cursor) for r in second
    ]

    # Past the latest watermark, nothing is re-surfaced.
    watermark = max((r.cursor for r in first if r.cursor), default=None)
    assert watermark is not None
    assert await connector.discover(watermark) == []


@pytest.mark.parametrize("name", CONNECTORS)
async def test_fetch_is_content_addressed_and_repeatable(name, connectors_root, workspace) -> None:
    connector = _make(name, connectors_root, workspace)
    ref = (await connector.discover(None))[0]

    first, data_a = await connector.fetch_with_bytes(ref)
    second, data_b = await connector.fetch_with_bytes(ref)
    assert first.id == second.id  # deterministic, content-addressed id
    assert data_a == data_b
    assert first.content_hash == second.content_hash
