"""Invite links: admin mints one; redeeming it (no auth) provisions and signs in a user."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _bearer(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_id}"}


def _admin_with_workspace(client: TestClient, op: dict[str, str]) -> tuple[str, str]:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    admin = client.post(
        "/users",
        json={"organization_id": org_id, "email": "admin@acme.example", "display_name": "Admin"},
        headers=op,
    ).json()["id"]
    ws = client.post(
        "/workspaces", json={"name": "Shared", "kind": "shared"}, headers=_bearer(admin)
    ).json()["id"]
    return admin, ws


def test_admin_mints_and_invitee_redeems(client: TestClient, op: dict[str, str]) -> None:
    admin, ws = _admin_with_workspace(client, op)

    mint = client.post(f"/workspaces/{ws}/invites", json={"role": "member"}, headers=_bearer(admin))
    assert mint.status_code == 201, mint.text
    token = mint.json()["token"]
    assert token
    assert mint.json()["redeemed"] is False

    # The invitee redeems with no auth — the token is the secret.
    redeem = client.post(
        f"/invites/{token}/redeem",
        json={"email": "new@acme.example", "display_name": "Newbie"},
    )
    assert redeem.status_code == 200, redeem.text
    new_user = redeem.json()["user_id"]

    # Signed in (bearer = user id): the new user has a personal workspace and joined the shared one.
    workspaces = client.get("/workspaces", headers=_bearer(new_user)).json()
    assert any(w["kind"] == "personal" for w in workspaces)
    assert ws in {w["id"] for w in workspaces}

    # Single-use: the token cannot be redeemed again.
    again = client.post(
        f"/invites/{token}/redeem",
        json={"email": "other@acme.example", "display_name": "Other"},
    )
    assert again.status_code == 409


def test_minting_requires_workspace_admin(client: TestClient, op: dict[str, str]) -> None:
    admin, ws = _admin_with_workspace(client, op)
    org_id = client.get("/users/me", headers=_bearer(admin)).json()["organization_id"]
    outsider = client.post(
        "/users",
        json={"organization_id": org_id, "email": "out@acme.example", "display_name": "Out"},
        headers=op,
    ).json()["id"]
    resp = client.post(f"/workspaces/{ws}/invites", json={}, headers=_bearer(outsider))
    assert resp.status_code == 403


def test_unknown_invite_token_is_404(client: TestClient, op: dict[str, str]) -> None:
    resp = client.post(
        "/invites/nope/redeem", json={"email": "x@acme.example", "display_name": "X"}
    )
    assert resp.status_code == 404
