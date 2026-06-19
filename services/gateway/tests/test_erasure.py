"""Right-to-erasure through the gateway: admin-gated, workspace-resolved artifact deletion.

The fast cases run on the in-memory backend (no Docker): only a workspace admin can erase, a
non-member is denied by the isolation gate, and an unknown id is a 404. The durable cascade (drop
the derived graph + physically erase the raw blob) is asserted against Postgres + MinIO.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from metis_gateway.app import create_app
from metis_gateway.settings import GatewaySettings

_APOLLO = "Ada leads the Apollo project."


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


def _ingest_apollo(client: TestClient, ws: str, headers: dict[str, str]) -> str:
    """Ingest the Apollo note into ``ws`` and return the artifact id behind the cited answer."""
    ingest = client.post(
        f"/workspaces/{ws}/ingest",
        json={"filename": "note.md", "content": _APOLLO},
        headers=headers,
    )
    assert ingest.status_code == 202, ingest.text
    answer = client.post(f"/workspaces/{ws}/query", json={"text": "Apollo"}, headers=headers)
    assert answer.status_code == 200, answer.text
    citations = answer.json()["citations"]
    assert citations, answer.text
    artifact_id: str = citations[0]["artifact_id"]
    assert artifact_id, answer.text
    return artifact_id


def test_owner_can_erase_own_artifact(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    artifact_id = _ingest_apollo(client, ada_ws, _bearer(ada))

    erased = client.delete(f"/workspaces/{ada_ws}/artifacts/{artifact_id}", headers=_bearer(ada))
    assert erased.status_code == 200, erased.text
    body = erased.json()
    assert body["artifact_tombstoned"] is True
    assert body["claims"] >= 1

    # The evidence is gone: the same query no longer has grounded support.
    after = client.post(
        f"/workspaces/{ada_ws}/query", json={"text": "Apollo"}, headers=_bearer(ada)
    )
    assert after.json()["sufficient"] is False


def test_non_member_cannot_erase_anothers_artifact(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    grace = _provision(client, op, org_id, "grace@acme.example")
    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    artifact_id = _ingest_apollo(client, ada_ws, _bearer(ada))

    # Grace is not a member of Ada's workspace: the isolation gate denies before erasure runs.
    blocked = client.delete(f"/workspaces/{ada_ws}/artifacts/{artifact_id}", headers=_bearer(grace))
    assert blocked.status_code == 403

    # And Ada's evidence is untouched.
    after = client.post(
        f"/workspaces/{ada_ws}/query", json={"text": "Apollo"}, headers=_bearer(ada)
    )
    assert after.json()["sufficient"] is True


def test_viewer_cannot_erase(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    grace = _provision(client, op, org_id, "grace@acme.example")

    shared = client.post("/workspaces", json={"name": "Project X"}, headers=_bearer(ada))
    shared_ws = shared.json()["id"]
    client.post(
        f"/workspaces/{shared_ws}/members",
        json={"user_id": grace, "role": "viewer"},
        headers=_bearer(ada),
    )
    artifact_id = _ingest_apollo(client, shared_ws, _bearer(ada))

    # A viewer may read the workspace but erasure is admin-only.
    denied = client.delete(
        f"/workspaces/{shared_ws}/artifacts/{artifact_id}", headers=_bearer(grace)
    )
    assert denied.status_code == 403


def test_erase_unknown_artifact_is_404(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    missing = client.delete(f"/workspaces/{ada_ws}/artifacts/art_{'0' * 32}", headers=_bearer(ada))
    assert missing.status_code == 404


def test_erase_cascades_and_deletes_blob_durably(pg_settings: GatewaySettings) -> None:
    """On the durable backend, erasure tombstones the derived graph *and* erases the raw blob."""
    op = {"Authorization": "Bearer op-token"}
    with TestClient(create_app(pg_settings)) as client:
        org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
        ada = _provision(client, op, org_id, "ada@acme.example")
        ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

        artifact_id = _ingest_apollo(client, ada_ws, _bearer(ada))

        erased = client.delete(
            f"/workspaces/{ada_ws}/artifacts/{artifact_id}", headers=_bearer(ada)
        )
        assert erased.status_code == 200, erased.text
        body = erased.json()
        assert body["artifact_tombstoned"] is True
        assert body["claims"] >= 1
        assert body["blobs_erased"] >= 1  # the raw blob is physically gone, not just tombstoned

        after = client.post(
            f"/workspaces/{ada_ws}/query", json={"text": "Apollo"}, headers=_bearer(ada)
        )
        assert after.json()["sufficient"] is False
