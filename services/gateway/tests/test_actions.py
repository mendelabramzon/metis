"""The proposed-action command surface: a command is interpreted into a typed action (a read-only
ANSWER without a model), listed/inspected, and approved/rejected with the actor + decision recorded.
"""

from __future__ import annotations


def _propose(client, op, command: str = "what did we ship?") -> dict:
    resp = client.post("/actions", json={"command": command}, headers=op)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_propose_interprets_and_persists(client, op) -> None:
    action = _propose(client, op)
    assert action["kind"] == "answer"  # the no-model fallback
    assert action["risk"] == "read_only"
    assert action["status"] == "proposed"
    assert action["command"] == "what did we ship?"
    assert action["parameters"] == {"query": "what did we ship?"}

    listed = client.get("/actions", headers=op).json()
    assert any(a["id"] == action["id"] for a in listed)
    fetched = client.get(f"/actions/{action['id']}", headers=op)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == action["id"]


def test_approve_records_the_decision(client, op) -> None:
    action = _propose(client, op)

    approved = client.post(
        f"/actions/{action['id']}/approve", json={"note": "looks right"}, headers=op
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "approved"
    assert body["decided_by"]
    assert body["decision_note"] == "looks right"

    again = client.post(f"/actions/{action['id']}/approve", json={}, headers=op)
    assert again.status_code == 409  # a decided action cannot be re-decided


def test_reject_filters_in_the_inbox(client, op) -> None:
    action = _propose(client, op)
    rejected = client.post(f"/actions/{action['id']}/reject", json={}, headers=op)
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    inbox = client.get("/actions?status=rejected", headers=op).json()
    assert [a["id"] for a in inbox] == [action["id"]]


def test_unknown_action_is_404(client, op) -> None:
    assert client.get("/actions/act_" + "0" * 32, headers=op).status_code == 404
