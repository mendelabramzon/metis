"""Uploaded-documents surface: a member lists and erases the files they uploaded.

Uploads register no source, so they never appear under /sources; this is their list + delete
surface. Covered on the in-memory backend for the HTTP contract + gating, and against Postgres for
the real JSONB scoping + tombstone cascade.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from metis_gateway.app import create_app
from metis_gateway.settings import GatewaySettings

_OP = {"Authorization": "Bearer op-token"}


def _provision(client: TestClient, op: dict[str, str], org_id: str, email: str) -> str:
    resp = client.post(
        "/users",
        json={"organization_id": org_id, "email": email, "display_name": email.split("@")[0]},
        headers=op,
    )
    assert resp.status_code == 201, resp.text
    user_id: str = resp.json()["id"]
    return user_id


def _bearer(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_id}"}


def _ada_workspace(client: TestClient, op: dict[str, str]) -> tuple[str, dict[str, str], str]:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]
    return org_id, _bearer(ada), ws


def _upload(client: TestClient, ws: str, auth: dict[str, str], name: str, body: bytes) -> None:
    resp = client.post(f"/workspaces/{ws}/upload", files=[("files", (name, body))], headers=auth)
    assert resp.status_code == 201, resp.text


def test_uploads_are_listed_newest_first(client: TestClient, op: dict[str, str]) -> None:
    _, ada, ws = _ada_workspace(client, op)
    _upload(client, ws, ada, "first.txt", b"Ada Lovelace is the CTO of Acme Inc.")
    _upload(client, ws, ada, "second.txt", b"Acme was founded in 2019.")

    docs = client.get(f"/workspaces/{ws}/documents", headers=ada)
    assert docs.status_code == 200, docs.text
    listed = docs.json()
    assert [d["filename"] for d in listed] == ["second.txt", "first.txt"]  # newest first
    assert all(d["connector"] == "upload" for d in listed)
    assert all(d["artifact_id"] and not d["tombstoned"] for d in listed)


def test_delete_removes_an_uploaded_document(client: TestClient, op: dict[str, str]) -> None:
    _, ada, ws = _ada_workspace(client, op)
    _upload(client, ws, ada, "notes.txt", b"Ada Lovelace is the CTO of Acme Inc.")
    [doc] = client.get(f"/workspaces/{ws}/documents", headers=ada).json()

    deleted = client.delete(f"/workspaces/{ws}/documents/{doc['artifact_id']}", headers=ada)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["artifact_tombstoned"] is True

    assert client.get(f"/workspaces/{ws}/documents", headers=ada).json() == []
    # Re-deleting the now-tombstoned document is a 404, not a double erase.
    assert (
        client.delete(f"/workspaces/{ws}/documents/{doc['artifact_id']}", headers=ada).status_code
        == 404
    )


def test_delete_unknown_document_is_404(client: TestClient, op: dict[str, str]) -> None:
    _, ada, ws = _ada_workspace(client, op)
    missing = client.delete(f"/workspaces/{ws}/documents/art_{'0' * 32}", headers=ada)
    assert missing.status_code == 404


def test_documents_are_membership_gated(client: TestClient, op: dict[str, str]) -> None:
    org_id, ada, ws = _ada_workspace(client, op)
    _upload(client, ws, ada, "notes.txt", b"secret")
    grace = _provision(client, op, org_id, "grace@acme.example")  # same org, not a member

    assert client.get(f"/workspaces/{ws}/documents", headers=_bearer(grace)).status_code == 403
    assert (
        client.delete(f"/workspaces/{ws}/documents/art_x", headers=_bearer(grace)).status_code
        == 403
    )


def test_delete_uploaded_document_durably_erases_evidence(pg_settings: GatewaySettings) -> None:
    """Against Postgres: the JSONB scoping lists exactly the uploads, and deleting one runs the
    real tombstone cascade so its evidence stops backing answers."""
    with TestClient(create_app(pg_settings)) as client:
        _, ada, ws = _ada_workspace(client, _OP)
        _upload(client, ws, ada, "acme.txt", b"Ada Lovelace is the CTO of Acme Inc.")

        [doc] = client.get(f"/workspaces/{ws}/documents", headers=ada).json()
        assert doc["connector"] == "upload"

        answered = client.post(
            f"/workspaces/{ws}/query", json={"text": "Who is the CTO of Acme?"}, headers=ada
        ).json()
        assert answered["sufficient"] is True

        deleted = client.delete(f"/workspaces/{ws}/documents/{doc['artifact_id']}", headers=ada)
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["blobs_erased"] == 1  # the raw blob is physically gone

        assert client.get(f"/workspaces/{ws}/documents", headers=ada).json() == []
        # Its evidence is tombstoned, so retrieval no longer finds it — the answer is insufficient.
        regone = client.post(
            f"/workspaces/{ws}/query", json={"text": "Who is the CTO of Acme?"}, headers=ada
        ).json()
        assert regone["sufficient"] is False
