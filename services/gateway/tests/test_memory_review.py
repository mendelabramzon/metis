"""Memory review: list active memory cells (member-gated), retract/supersede them (writer-gated).

The in-memory backend builds no memory cells, so those cases cover the HTTP contract + gates. The
Postgres case ingests evidence (which consolidates a mem cell), then walks the review loop.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from metis_gateway.app import create_app
from metis_gateway.settings import GatewaySettings


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


def test_empty_memory_and_unknown_revise_404(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    listed = client.get(f"/workspaces/{ada_ws}/memory", headers=_bearer(ada))
    assert listed.status_code == 200
    assert listed.json() == []  # the in-memory backend builds no memory cells

    retract = client.post(
        f"/workspaces/{ada_ws}/memory/mc_{'0' * 32}/retract", json={}, headers=_bearer(ada)
    )
    assert retract.status_code == 404


def test_memory_list_is_member_gated(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    grace = _provision(client, op, org_id, "grace@acme.example")
    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    blocked = client.get(f"/workspaces/{ada_ws}/memory", headers=_bearer(grace))
    assert blocked.status_code == 403


def test_revise_requires_writer(client: TestClient, op: dict[str, str]) -> None:
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

    # A viewer may read the memory but cannot revise it — the writer gate denies first.
    assert client.get(f"/workspaces/{shared_ws}/memory", headers=_bearer(grace)).status_code == 200
    denied = client.post(
        f"/workspaces/{shared_ws}/memory/mc_{'0' * 32}/supersede", json={}, headers=_bearer(grace)
    )
    assert denied.status_code == 403


def _ingest(client: TestClient, ws: str, headers: dict[str, str], content: str) -> None:
    resp = client.post(
        f"/workspaces/{ws}/ingest",
        json={"filename": "note.md", "content": content},
        headers=headers,
    )
    assert resp.status_code == 202, resp.text


def test_memory_review_retract_and_supersede_durable(pg_settings: GatewaySettings) -> None:
    op = {"Authorization": "Bearer op-token"}
    with TestClient(create_app(pg_settings)) as client:
        org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
        # Gateway Postgres fixtures share one DB across tests; use an email unique to this test.
        ada = _provision(client, op, org_id, "ada-memory@acme.example")
        ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

        # Ingestion consolidates the claims into a memory cell, which the review queue lists.
        _ingest(client, ws, _bearer(ada), "Ada Lovelace leads the Apollo project.")
        cells = client.get(f"/workspaces/{ws}/memory", headers=_bearer(ada)).json()
        assert len(cells) == 1
        assert cells[0]["summary"]
        assert cells[0]["claim_ids"]

        # Retract it — it drops out of active memory.
        retract = client.post(
            f"/workspaces/{ws}/memory/{cells[0]['mem_cell_id']}/retract",
            json={"reason": "superseded by a correction"},
            headers=_bearer(ada),
        )
        assert retract.status_code == 200, retract.text
        assert retract.json()["op"] == "retract"
        assert client.get(f"/workspaces/{ws}/memory", headers=_bearer(ada)).json() == []

        # A second cell can be marked stale (superseded) instead, also dropping from active memory.
        _ingest(client, ws, _bearer(ada), "Grace Hopper joined the Mercury project in 2020.")
        second = client.get(f"/workspaces/{ws}/memory", headers=_bearer(ada)).json()
        assert len(second) == 1
        superseded = client.post(
            f"/workspaces/{ws}/memory/{second[0]['mem_cell_id']}/supersede",
            json={},
            headers=_bearer(ada),
        )
        assert superseded.status_code == 200, superseded.text
        assert superseded.json()["op"] == "supersede"
        assert client.get(f"/workspaces/{ws}/memory", headers=_bearer(ada)).json() == []
