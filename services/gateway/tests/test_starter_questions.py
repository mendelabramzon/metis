"""Starter questions: a few grounded, answerable questions for a freshly-populated workspace (A5).

Runs on the in-memory backend (no Docker, no model), so the deterministic fallback generates the
questions from the ingested claims. The operator provisions identity; the user acts as themselves.
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


def test_starter_questions_appear_after_content_lands(
    client: TestClient, op: dict[str, str]
) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    # An empty workspace has nothing grounded to suggest yet.
    empty = client.get(f"/workspaces/{ws}/starter-questions", headers=_bearer(ada))
    assert empty.status_code == 200, empty.text
    assert empty.json()["questions"] == []

    client.post(
        f"/workspaces/{ws}/ingest",
        json={
            "filename": "memo.md",
            "content": (
                "Apollo launches in March 2026. The Apollo budget is fifty thousand dollars. "
                "Ada leads the Apollo project."
            ),
        },
        headers=_bearer(ada),
    )

    resp = client.get(f"/workspaces/{ws}/starter-questions", headers=_bearer(ada))
    assert resp.status_code == 200, resp.text
    questions = resp.json()["questions"]
    assert questions, "expected grounded starter questions once the workspace has evidence"
    assert all(isinstance(q, str) and q.strip() for q in questions)
    assert len(questions) <= 3


def test_starter_questions_are_membership_gated(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    grace = _provision(client, op, org_id, "grace@acme.example")
    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    # A non-member cannot read another user's starter questions (the isolation gate).
    denied = client.get(f"/workspaces/{ada_ws}/starter-questions", headers=_bearer(grace))
    assert denied.status_code == 403
