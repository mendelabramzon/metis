"""POST /sources/{id}/sync enqueues a connector-sync job, so a source ingests end-to-end via a
durable *queued* job (the acceptance criterion) rather than an inline POST. The queued job is
visible on the operator jobs surface; an unknown source is a 404."""

from __future__ import annotations


def _register_source(client, op) -> str:
    created = client.post(
        "/sources",
        json={"name": "mailbox", "connector": "imap", "sensitivity": "confidential"},
        headers=op,
    )
    assert created.status_code == 201, created.text
    source_id: str = created.json()["id"]
    return source_id


def test_sync_enqueues_a_connector_poll_job(client, op) -> None:
    source_id = _register_source(client, op)

    resp = client.post(f"/sources/{source_id}/sync", headers=op)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["source_id"] == source_id
    assert body["job_id"]

    # The queued job is visible to operators (the ingest worker leases ingest.poll jobs).
    jobs = client.get("/jobs", headers=op).json()
    assert any(j["id"] == body["job_id"] and j["kind"] == "ingest.poll" for j in jobs)


def test_sync_unknown_source_is_404(client, op) -> None:
    resp = client.post("/sources/src_" + "0" * 32 + "/sync", headers=op)
    assert resp.status_code == 404


def test_sync_requires_operator(client, user) -> None:
    assert client.post("/sources/src_" + "0" * 32 + "/sync", headers=user).status_code == 403
