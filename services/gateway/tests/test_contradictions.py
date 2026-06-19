"""Contradiction inbox: list conflicting evidence (member-gated), resolve/dismiss it (writer-gated).

The maintainer detects and persists contradictions; the in-memory backend has none, so those cases
cover the HTTP contract + gates. The Postgres case seeds one and walks the review flow.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.stores import PostgresMemoryStore
from metis_gateway.app import create_app
from metis_gateway.settings import GatewaySettings
from metis_protocol import ContradictionId, WorkspaceId, new_id
from metis_protocol.examples import contradiction as _example_contradiction


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


def test_empty_inbox_and_unknown_resolve_404(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    inbox = client.get(f"/workspaces/{ada_ws}/contradictions", headers=_bearer(ada))
    assert inbox.status_code == 200
    assert inbox.json() == []  # the in-memory backend detects no contradictions

    resolve = client.patch(
        f"/workspaces/{ada_ws}/contradictions/ctr_{'0' * 32}",
        json={"status": "resolved"},
        headers=_bearer(ada),
    )
    assert resolve.status_code == 404


def test_inbox_is_member_gated(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    grace = _provision(client, op, org_id, "grace@acme.example")
    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    blocked = client.get(f"/workspaces/{ada_ws}/contradictions", headers=_bearer(grace))
    assert blocked.status_code == 403


def test_resolve_requires_writer(client: TestClient, op: dict[str, str]) -> None:
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

    # A viewer may read the inbox but cannot resolve — the writer gate denies before any lookup.
    assert (
        client.get(f"/workspaces/{shared_ws}/contradictions", headers=_bearer(grace)).status_code
        == 200
    )
    denied = client.patch(
        f"/workspaces/{shared_ws}/contradictions/ctr_{'0' * 32}",
        json={"status": "dismissed"},
        headers=_bearer(grace),
    )
    assert denied.status_code == 403


def _seed_contradiction(sessionmaker: async_sessionmaker[AsyncSession], workspace_id: str) -> str:
    """Persist an open contradiction in a workspace (as the maintainer would); return its id."""
    base = _example_contradiction()
    seeded = base.model_copy(
        update={
            "id": new_id(ContradictionId),
            "provenance": base.provenance.model_copy(
                update={"workspace_id": WorkspaceId(workspace_id)}
            ),
        }
    )

    async def _write() -> None:
        await PostgresMemoryStore(sessionmaker).write_contradiction(seeded)

    asyncio.run(_write())
    return str(seeded.id)


def test_contradiction_inbox_durable(
    pg_settings: GatewaySettings, pg_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    op = {"Authorization": "Bearer op-token"}
    with TestClient(create_app(pg_settings)) as client:
        org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
        # Gateway Postgres fixtures share one DB across tests; use an email unique to this test.
        ada = _provision(client, op, org_id, "ada-contradiction@acme.example")
        ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]
        cid = _seed_contradiction(pg_sessionmaker, ada_ws)

        # The inbox surfaces the open contradiction with its conflicting claim ids.
        inbox = client.get(f"/workspaces/{ada_ws}/contradictions", headers=_bearer(ada)).json()
        item = next(c for c in inbox if c["contradiction_id"] == cid)
        assert item["status"] == "open"
        assert len(item["claim_ids"]) >= 2

        # A writer resolves it.
        resolved = client.patch(
            f"/workspaces/{ada_ws}/contradictions/{cid}",
            json={"status": "resolved"},
            headers=_bearer(ada),
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "resolved"

        # It drops out of the open inbox and shows under resolved.
        still_open = client.get(f"/workspaces/{ada_ws}/contradictions", headers=_bearer(ada)).json()
        assert all(c["contradiction_id"] != cid for c in still_open)
        resolved_list = client.get(
            f"/workspaces/{ada_ws}/contradictions?status=resolved", headers=_bearer(ada)
        ).json()
        assert any(c["contradiction_id"] == cid for c in resolved_list)
