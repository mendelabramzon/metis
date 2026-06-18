"""The main engine loop over HTTP: register a source, ingest, query, get a cited answer."""

from __future__ import annotations


def test_health_and_ui_are_served(client) -> None:
    assert client.get("/health").json()["status"] == "ok"
    page = client.get("/")
    assert page.status_code == 200
    assert "Metis" in page.text  # the debug console shell


def test_ingest_then_query_returns_a_cited_answer(client, op, user) -> None:
    created = client.post(
        "/sources",
        json={"name": "notes", "connector": "web_clip", "sensitivity": "internal"},
        headers=op,
    )
    assert created.status_code == 201
    source_id = created.json()["id"]

    ingested = client.post(
        f"/sources/{source_id}/ingest",
        json={
            "filename": "acme.txt",
            "content": "Ada Lovelace is the CTO of Acme Inc. Acme was founded in 2019.",
        },
        headers=op,
    )
    assert ingested.status_code == 202
    assert ingested.json()["claims"] >= 1

    answered = client.post("/query", json={"text": "Who is the CTO of Acme?"}, headers=user)
    assert answered.status_code == 200
    body = answered.json()
    assert body["sufficient"] is True
    assert "Ada" in body["answer"]
    assert body["citations"]  # the answer is grounded in cited evidence
    assert body["citations"][0]["claim_id"]


def test_unauthenticated_requests_are_rejected(client) -> None:
    assert client.get("/sources").status_code == 401
    assert client.post("/query", json={"text": "hi"}).status_code == 401
