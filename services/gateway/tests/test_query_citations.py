"""Query responses carry citations to source-backed evidence (and stay honest when they can't)."""

from __future__ import annotations


def _ingest(client, op, content: str, filename: str = "memo.txt") -> None:
    source_id = client.post(
        "/sources",
        json={"name": "s", "connector": "web_clip", "sensitivity": "internal"},
        headers=op,
    ).json()["id"]
    client.post(
        f"/sources/{source_id}/ingest",
        json={"filename": filename, "content": content},
        headers=op,
    )


def test_citations_point_to_claims_and_source_spans(client, op, user) -> None:
    _ingest(client, op, "Grace Hopper joined Acme in 2020.")

    body = client.post("/query", json={"text": "When did Grace Hopper join?"}, headers=user).json()

    assert body["sufficient"] is True
    assert body["citations"]
    citation = body["citations"][0]
    assert citation["claim_id"]
    assert citation["source_span_id"]  # traceable to a source span
    assert citation["artifact_id"]
    assert citation["sensitivity"] == "internal"  # the cited claim's tier travels with the citation


def test_insufficient_evidence_is_honest_and_uncited(client, user) -> None:
    body = client.post("/query", json={"text": "What is the annual revenue?"}, headers=user).json()
    assert body["sufficient"] is False
    assert body["citations"] == []
