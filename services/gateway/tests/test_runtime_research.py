"""POST /workspaces/{ws}/runtime/research enqueues a background research job (membership-gated).

The producer side of the runtime worker: a member queues a research job into the durable queue the
runtime worker leases from; a non-member is refused by the isolation gate. The worker's processing
(answer -> fileback proposal) is covered in the runtime package's own suite.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from metis_protocol import WorkspaceId


def _user(client: TestClient, op: dict[str, str], *, email: str) -> tuple[dict[str, str], str]:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    user_id = client.post(
        "/users",
        json={"organization_id": org_id, "email": email, "display_name": email.split("@")[0]},
        headers=op,
    ).json()["id"]
    auth = {"Authorization": f"Bearer {user_id}"}
    workspace_id = client.get("/workspaces", headers=auth).json()[0]["id"]
    return auth, workspace_id


def test_research_enqueues_a_runtime_job(client: TestClient, op: dict[str, str]) -> None:
    ada, ws = _user(client, op, email="ada@acme.example")
    resp = client.post(
        f"/workspaces/{ws}/runtime/research", json={"query": "what did we ship?"}, headers=ada
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["kind"] == "runtime.research"
    assert body["job_id"]

    # the job is really on the durable queue the runtime worker leases from
    jobs = asyncio.run(client.app.state.backend.jobs.list(WorkspaceId(ws)))
    assert any(str(j.id) == body["job_id"] and j.kind == "runtime.research" for j in jobs)


def test_research_requires_membership(client: TestClient, op: dict[str, str]) -> None:
    _ada, ws = _user(client, op, email="ada@acme.example")
    bob, _bob_ws = _user(client, op, email="bob@other.example")  # a different org/workspace
    resp = client.post(f"/workspaces/{ws}/runtime/research", json={"query": "x"}, headers=bob)
    assert resp.status_code == 403  # the isolation gate: not a member of Ada's workspace
