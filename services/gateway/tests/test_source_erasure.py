"""Deleting a source: operator-gated, removes the registration, returns an erasure summary.

The artifact-cascade mechanics are covered against Postgres in metis-ingestion's
``test_source_erasure``; here we assert the HTTP contract on the in-memory backend (which records no
source provenance, so the erasure counts are zero but the registration is still removed).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_source(client: TestClient, op: dict[str, str]) -> str:
    resp = client.post(
        "/sources",
        json={"name": "docs", "connector": "web_clip", "sensitivity": "internal"},
        headers=op,
    )
    assert resp.status_code == 201, resp.text
    source_id: str = resp.json()["id"]
    return source_id


def test_operator_deletes_a_source(client: TestClient, op: dict[str, str]) -> None:
    source_id = _create_source(client, op)
    assert any(s["id"] == source_id for s in client.get("/sources", headers=op).json())

    deleted = client.delete(f"/sources/{source_id}", headers=op)
    assert deleted.status_code == 200, deleted.text
    assert set(deleted.json()) == {"artifacts", "claims", "mem_cells", "blobs_erased"}

    # The registration is gone, so a re-delete is a 404.
    assert all(s["id"] != source_id for s in client.get("/sources", headers=op).json())
    assert client.delete(f"/sources/{source_id}", headers=op).status_code == 404


def test_delete_unknown_source_is_404(client: TestClient, op: dict[str, str]) -> None:
    assert client.delete(f"/sources/src_{'0' * 32}", headers=op).status_code == 404


def test_delete_source_requires_operator(
    client: TestClient, op: dict[str, str], user: dict[str, str]
) -> None:
    source_id = _create_source(client, op)
    assert client.delete(f"/sources/{source_id}", headers=user).status_code == 403
