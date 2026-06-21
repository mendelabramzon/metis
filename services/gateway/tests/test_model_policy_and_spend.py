"""Per-workspace model policy + spend: admin-managed policy, spend visibility, and a daily cap.

The API tests run on the in-memory backend (no Docker). The cap path seeds the in-process
SpendTracker directly, since the in-memory query uses the deterministic extractor and makes no real
model calls — so there is no spend to accumulate organically.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from metis_gateway.models import SpendTracker, over_daily_cap
from metis_protocol import AuditEvent, WorkspaceModelPolicy

_WS = "ws_" + "9" * 32


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


def _ada_and_workspace(client: TestClient, op: dict[str, str]) -> tuple[str, str]:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]
    return ada, ws


# --- unit: the tracker + the cap helper --------------------------------------------------------


class _Sink:
    async def emit(self, event: AuditEvent) -> None:  # pragma: no cover - not exercised here
        return None


def test_spend_tracker_accumulates_by_task() -> None:
    tracker = SpendTracker(_Sink())
    tracker.record(_WS, "query_answer", 0.4)
    tracker.record(_WS, "query_answer", 0.1)
    tracker.record(_WS, "extract_claims", 0.25)
    assert tracker.today_total(_WS) == 0.75
    assert tracker.today_by_task(_WS) == {"query_answer": 0.5, "extract_claims": 0.25}


def test_over_daily_cap() -> None:
    capped = WorkspaceModelPolicy(workspace_id=_WS, daily_cost_cap_usd=1.0)
    assert over_daily_cap(capped, 1.0) is True
    assert over_daily_cap(capped, 0.9) is False
    assert over_daily_cap(WorkspaceModelPolicy(workspace_id=_WS), 999.0) is False  # no cap set


# --- API: policy management, spend visibility, cap enforcement ---------------------------------


def test_model_policy_defaults_and_roundtrips(client: TestClient, op: dict[str, str]) -> None:
    ada, ws = _ada_and_workspace(client, op)

    default = client.get(f"/workspaces/{ws}/model-policy", headers=_bearer(ada))
    assert default.status_code == 200
    assert default.json()["allow_external_models"] is True
    assert default.json()["daily_cost_cap_usd"] is None

    put = client.put(
        f"/workspaces/{ws}/model-policy",
        json={"allow_external_models": False, "daily_cost_cap_usd": 5.0},
        headers=_bearer(ada),
    )
    assert put.status_code == 200
    got = client.get(f"/workspaces/{ws}/model-policy", headers=_bearer(ada)).json()
    assert got["allow_external_models"] is False
    assert got["daily_cost_cap_usd"] == 5.0


def test_policy_is_admin_gated(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    grace = _provision(client, op, org_id, "grace@acme.example")
    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    # Grace is not a member of Ada's workspace: she can neither read nor set its policy.
    read = client.get(f"/workspaces/{ada_ws}/model-policy", headers=_bearer(grace))
    assert read.status_code == 403
    write = client.put(
        f"/workspaces/{ada_ws}/model-policy",
        json={"allow_external_models": False},
        headers=_bearer(grace),
    )
    assert write.status_code == 403


def test_spend_visible_and_cap_blocks_query(client: TestClient, op: dict[str, str]) -> None:
    ada, ws = _ada_and_workspace(client, op)

    # Seed spend directly (the in-memory query path makes no real model call).
    backend: Any = client.app.state.backend
    backend.spend.record(ws, "query_answer", 1.0)

    spend = client.get(f"/workspaces/{ws}/spend", headers=_bearer(ada))
    assert spend.status_code == 200
    assert spend.json()["today_total_usd"] == 1.0

    # A cap below today's spend blocks the next query with 429.
    client.put(
        f"/workspaces/{ws}/model-policy", json={"daily_cost_cap_usd": 0.5}, headers=_bearer(ada)
    )
    blocked = client.post(
        f"/workspaces/{ws}/query", json={"text": "anything"}, headers=_bearer(ada)
    )
    assert blocked.status_code == 429


def test_routing_outcome_is_local_when_external_forbidden(
    client: TestClient, op: dict[str, str]
) -> None:
    ada, ws = _ada_and_workspace(client, op)
    client.put(
        f"/workspaces/{ws}/model-policy",
        json={"allow_external_models": False},
        headers=_bearer(ada),
    )
    client.post(
        f"/workspaces/{ws}/ingest",
        json={"filename": "n.md", "content": "Ada leads the Apollo project."},
        headers=_bearer(ada),
    )
    body = client.post(
        f"/workspaces/{ws}/query", json={"text": "Apollo"}, headers=_bearer(ada)
    ).json()
    # External is forbidden by policy, so the answer is guaranteed on-device (A2).
    assert body["routed_local"] is True
