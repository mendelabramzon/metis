"""Approving an action is explicit, runs through the inbox, and is recorded in the audit log."""

from __future__ import annotations

_RUN = {"name": "announce", "version": "1.0.0", "arguments": {"message": "ship it"}}


def test_action_approval_is_explicit_and_audited(client, op) -> None:
    # An outbound skill is held, not executed.
    held = client.post("/skills/run", json=_RUN, headers=op).json()
    assert held["outcome"] == "needs_approval"
    assert held["approval_required"] is True

    # It surfaces in the unified inbox.
    inbox = client.get("/approvals", headers=op).json()
    action = next(item for item in inbox if item["kind"] == "action")

    # A human approves it explicitly.
    approved = client.post(
        f"/approvals/action/{action['id']}/approve", json={"note": "ok"}, headers=op
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    # The decision is on the audit record, attributed to the operator.
    audit = client.get("/audit", params={"action": "approval.granted"}, headers=op).json()
    assert any(e["target_id"] == action["id"] and e["actor"] == "operator" for e in audit)

    # And the same run now executes.
    done = client.post("/skills/run", json=_RUN, headers=op).json()
    assert done["outcome"] == "success"
    assert done["output"] == {"sent": True}


def test_approvals_require_operator_scope(client, user) -> None:
    assert client.get("/approvals", headers=user).status_code == 403
