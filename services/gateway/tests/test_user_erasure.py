"""Erasing a user: operator-gated, purges their personal workspace and locks the account out.

The artifact-erasure mechanics are covered against Postgres in metis-ingestion; here we assert the
HTTP contract on the in-memory backend, including that a deactivated user can no longer log in.
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


def test_erasing_a_user_purges_personal_data_and_locks_out(
    client: TestClient, op: dict[str, str]
) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    ingest = client.post(
        f"/workspaces/{ada_ws}/ingest",
        json={"filename": "note.md", "content": "Ada leads the Apollo project."},
        headers=_bearer(ada),
    )
    assert ingest.status_code == 202, ingest.text

    erased = client.delete(f"/users/{ada}", headers=op)
    assert erased.status_code == 200, erased.text
    body = erased.json()
    assert body["deactivated"] is True
    assert body["artifacts"] >= 1

    # The account is locked out: a deactivated (erased) user can no longer authenticate.
    assert client.get("/users/me", headers=_bearer(ada)).status_code == 401


def test_erase_unknown_user_is_404(client: TestClient, op: dict[str, str]) -> None:
    assert client.delete(f"/users/usr_{'0' * 32}", headers=op).status_code == 404


def test_erase_user_requires_operator(
    client: TestClient, op: dict[str, str], user: dict[str, str]
) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    assert client.delete(f"/users/{ada}", headers=user).status_code == 403
