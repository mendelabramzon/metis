"""The 'while you were away' digest: a per-workspace summary since a timestamp (A7, on-demand).

Runs on the in-memory backend, which detects no contradictions and builds no memory cells, so the
digest is empty here — the durable backend + maintainer populate it. These tests pin the endpoint
shape, the ``?since=`` handling, and the membership gate.
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


def test_digest_shape_on_a_fresh_workspace(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    body = client.get(f"/workspaces/{ws}/digest", headers=_bearer(ada))
    assert body.status_code == 200, body.text
    data = body.json()
    assert data["new_contradictions"] == 0
    assert data["contradictions"] == []
    assert data["new_facts"] == 0
    assert data["facts"] == []
    assert data["highlights"] == []


def test_digest_accepts_and_echoes_a_since_timestamp(
    client: TestClient, op: dict[str, str]
) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    ok = client.get(f"/workspaces/{ws}/digest?since=2026-01-01T00:00:00Z", headers=_bearer(ada))
    assert ok.status_code == 200
    assert ok.json()["since"] == "2026-01-01T00:00:00Z"

    # A malformed timestamp is tolerated (treated as "everything"), not a 4xx.
    junk = client.get(f"/workspaces/{ws}/digest?since=not-a-date", headers=_bearer(ada))
    assert junk.status_code == 200


def test_digest_is_membership_gated(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    grace = _provision(client, op, org_id, "grace@acme.example")
    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    denied = client.get(f"/workspaces/{ada_ws}/digest", headers=_bearer(grace))
    assert denied.status_code == 403


def test_weekly_window_is_accepted(client: TestClient, op: dict[str, str]) -> None:
    """The recurring weekly digest is the same endpoint with ``?window=week`` (trailing 7 days)."""
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    weekly = client.get(f"/workspaces/{ws}/digest?window=week", headers=_bearer(ada))
    assert weekly.status_code == 200, weekly.text
    body = weekly.json()
    assert body["new_contradictions"] == 0
    assert body["highlights"] == []


def test_weekly_digest_opt_in_defaults_on_and_toggles(
    client: TestClient, op: dict[str, str]
) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")

    # Defaulted on, and reflected on the user record.
    assert client.get("/users/me/preferences", headers=_bearer(ada)).json() == {
        "weekly_digest": True
    }
    assert client.get("/users/me", headers=_bearer(ada)).json()["weekly_digest_opt_in"] is True

    off = client.patch("/users/me/preferences", json={"weekly_digest": False}, headers=_bearer(ada))
    assert off.status_code == 200
    assert off.json() == {"weekly_digest": False}
    # The toggle persists for the next read.
    assert client.get("/users/me/preferences", headers=_bearer(ada)).json() == {
        "weekly_digest": False
    }


def test_accounts_selector_lists_active_accounts_without_auth(
    client: TestClient, op: dict[str, str]
) -> None:
    """The sign-in selector (C2) is pre-auth and never exposes a raw-id field; it lists accounts."""
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")

    accounts = client.get("/accounts")  # no Authorization header — backs the login picker
    assert accounts.status_code == 200, accounts.text
    rows = accounts.json()
    ada_row = next(r for r in rows if r["id"] == ada)
    assert ada_row == {"id": ada, "display_name": "ada", "email": "ada@acme.example"}

    # An erased (deactivated) account drops out of the selector.
    client.delete(f"/users/{ada}", headers=op)
    remaining = client.get("/accounts").json()
    assert all(r["id"] != ada for r in remaining)
