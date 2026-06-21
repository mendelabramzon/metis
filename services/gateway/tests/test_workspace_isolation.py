"""End-to-end workspace isolation through the gateway — the Stage 1 hard gate at the HTTP boundary.

A user cannot read another user's personal workspace: ``GET /workspaces/{other}`` returns 403,
because ``resolve_role`` finds no membership. Runs on the in-memory backend, so no Docker is needed.
The operator provisions identity (scope token); users then act as themselves (bearer = user id).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


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


def test_user_cannot_read_another_users_personal_workspace(
    client: TestClient, op: dict[str, str]
) -> None:
    org = client.post("/organizations", json={"name": "Acme"}, headers=op)
    assert org.status_code == 201, org.text
    org_id = org.json()["id"]

    ada = _provision(client, op, org_id, "ada@acme.example")
    grace = _provision(client, op, org_id, "grace@acme.example")

    ada_workspaces = client.get("/workspaces", headers=_bearer(ada)).json()
    assert len(ada_workspaces) == 1
    ada_ws = ada_workspaces[0]["id"]

    # Ada (a member) reads it; Grace (no membership) is denied — the isolation gate.
    assert client.get(f"/workspaces/{ada_ws}", headers=_bearer(ada)).status_code == 200
    assert client.get(f"/workspaces/{ada_ws}", headers=_bearer(grace)).status_code == 403

    # Grace's own listing never includes Ada's workspace.
    grace_ids = {w["id"] for w in client.get("/workspaces", headers=_bearer(grace)).json()}
    assert ada_ws not in grace_ids


def test_unauthenticated_and_unknown_tokens_are_rejected(client: TestClient) -> None:
    assert client.get("/workspaces").status_code == 401
    bad = client.get("/workspaces", headers={"Authorization": "Bearer not-a-user"})
    assert bad.status_code == 401


def test_me_returns_the_calling_user(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")

    me = client.get("/users/me", headers=_bearer(ada))
    assert me.status_code == 200
    assert me.json()["id"] == ada


def test_member_management_is_admin_gated(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    grace = _provision(client, op, org_id, "grace@acme.example")

    # Ada creates a shared workspace, so she owns it (and may administer it).
    shared = client.post("/workspaces", json={"name": "Project X"}, headers=_bearer(ada))
    assert shared.status_code == 201, shared.text
    shared_ws = shared.json()["id"]

    # Non-member Grace cannot administer.
    denied = client.get(f"/workspaces/{shared_ws}/members", headers=_bearer(grace))
    assert denied.status_code == 403

    # Ada adds Grace as a viewer: Grace can now read but still not administer.
    added = client.post(
        f"/workspaces/{shared_ws}/members",
        json={"user_id": grace, "role": "viewer"},
        headers=_bearer(ada),
    )
    assert added.status_code == 201, added.text
    assert client.get(f"/workspaces/{shared_ws}", headers=_bearer(grace)).status_code == 200
    assert client.get(f"/workspaces/{shared_ws}/members", headers=_bearer(grace)).status_code == 403


def test_workspace_engine_is_isolated(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    grace = _provision(client, op, org_id, "grace@acme.example")

    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]
    grace_ws = client.get("/workspaces", headers=_bearer(grace)).json()[0]["id"]

    # Ada ingests evidence into her own workspace.
    ingest = client.post(
        f"/workspaces/{ada_ws}/ingest",
        json={"filename": "note.md", "content": "Ada leads the Apollo project."},
        headers=_bearer(ada),
    )
    assert ingest.status_code == 202, ingest.text
    assert ingest.json()["claims"] >= 1

    # Ada queries her workspace and the answer rests on that evidence.
    ada_answer = client.post(
        f"/workspaces/{ada_ws}/query", json={"text": "Apollo"}, headers=_bearer(ada)
    )
    assert ada_answer.status_code == 200
    ada_body = ada_answer.json()
    assert ada_body["sufficient"] is True
    # Citations carry workspace scope + sensitivity (A1).
    ada_ws_kind = client.get("/workspaces", headers=_bearer(ada)).json()[0]["kind"]
    assert ada_body["citations"]
    assert ada_body["citations"][0]["scope"] == ada_ws_kind
    assert ada_body["citations"][0]["sensitivity"]

    # Grace can neither ingest into nor query Ada's workspace — she is not a member.
    blocked_ingest = client.post(
        f"/workspaces/{ada_ws}/ingest",
        json={"filename": "x.md", "content": "nope"},
        headers=_bearer(grace),
    )
    assert blocked_ingest.status_code == 403
    blocked_query = client.post(
        f"/workspaces/{ada_ws}/query", json={"text": "Apollo"}, headers=_bearer(grace)
    )
    assert blocked_query.status_code == 403

    # Cross-workspace isolation: Ada's evidence never leaks into Grace's own workspace.
    grace_answer = client.post(
        f"/workspaces/{grace_ws}/query", json={"text": "Apollo"}, headers=_bearer(grace)
    )
    assert grace_answer.status_code == 200
    assert grace_answer.json()["sufficient"] is False
