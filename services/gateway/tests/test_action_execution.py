"""Execution dispatch (POST /actions/{id}/execute): an approved/read-only action actually runs.

Risk gating is the human-agency control in HTTP form: a read-only action runs immediately; an
effectful one runs only after approval; an EXTERNAL one is blocked; and the memory/wiki write kinds
are deferred (they must flow through the pipeline / review inboxes, never a direct write). A run is
recorded EXECUTED and emits an audit event.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from metis_protocol import (
    ActionId,
    ActionKind,
    ActionRisk,
    ActionStatus,
    ProposedAction,
    Sensitivity,
    new_id,
)


def _inject(
    client: TestClient,
    *,
    kind: ActionKind,
    risk: ActionRisk,
    parameters: dict[str, object] | None = None,
    status: ActionStatus = ActionStatus.PROPOSED,
) -> str:
    """Persist a typed action straight into the store (the interpreter only yields read-only ANSWER
    without a model, so non-ANSWER kinds are injected to exercise the dispatch + gating)."""
    backend = client.app.state.backend  # type: ignore[attr-defined]
    action = ProposedAction(
        id=new_id(ActionId),
        workspace_id=backend.workspace_id,
        kind=kind,
        risk=risk,
        command="(injected)",
        summary=kind.value,
        parameters=parameters or {},
        sensitivity=Sensitivity.INTERNAL,
        audit_target=kind.value,
        status=status,
        created_at=datetime.now(UTC),
    )
    asyncio.run(backend.actions.propose(action))
    return str(action.id)


def _web_clip_source(client: TestClient, op: dict[str, str]) -> str:
    resp = client.post(
        "/sources", json={"name": "Clip", "connector": "web_clip", "config": {}}, headers=op
    )
    assert resp.status_code == 201, resp.text
    source_id: str = resp.json()["id"]
    return source_id


def test_read_only_runs_without_approval(client: TestClient, op: dict[str, str]) -> None:
    action = client.post("/actions", json={"command": "what did we ship?"}, headers=op).json()
    assert action["risk"] == "read_only"

    ran = client.post(f"/actions/{action['id']}/execute", headers=op)
    assert ran.status_code == 200, ran.text
    body = ran.json()
    assert body["action"]["status"] == "executed"
    assert body["answer"] is not None  # the query engine ran (no evidence yet -> not sufficient)

    again = client.post(f"/actions/{action['id']}/execute", headers=op)
    assert again.status_code == 409  # an executed action is not re-run


def test_effectful_needs_approval_then_queues_a_job(client: TestClient, op: dict[str, str]) -> None:
    source_id = _web_clip_source(client, op)
    action_id = _inject(
        client,
        kind=ActionKind.START_SYNC,
        risk=ActionRisk.REVERSIBLE,
        parameters={"source_id": source_id},
    )

    blocked = client.post(f"/actions/{action_id}/execute", headers=op)
    assert blocked.status_code == 409  # reversible: must be approved before it runs
    assert "approved" in blocked.json()["error"]["message"]

    client.post(f"/actions/{action_id}/approve", json={}, headers=op)
    ran = client.post(f"/actions/{action_id}/execute", headers=op)
    assert ran.status_code == 200, ran.text
    job_id = ran.json()["job_id"]
    assert job_id
    assert ran.json()["action"]["status"] == "executed"
    # the queued connector-sync job is real — visible to the ops surface the worker leases over.
    assert any(j["id"] == job_id for j in client.get("/jobs", headers=op).json())


def test_start_sync_without_a_source_is_a_clean_error(
    client: TestClient, op: dict[str, str]
) -> None:
    action_id = _inject(
        client,
        kind=ActionKind.START_SYNC,
        risk=ActionRisk.REVERSIBLE,
        status=ActionStatus.APPROVED,  # past the approval gate, but no source_id
    )
    resp = client.post(f"/actions/{action_id}/execute", headers=op)
    assert resp.status_code == 409
    assert "source_id" in resp.json()["error"]["message"]


def test_inspect_source_is_read_only(client: TestClient, op: dict[str, str]) -> None:
    source_id = _web_clip_source(client, op)
    action_id = _inject(
        client,
        kind=ActionKind.INSPECT_SOURCE,
        risk=ActionRisk.READ_ONLY,
        parameters={"source_id": source_id},
    )
    resp = client.post(f"/actions/{action_id}/execute", headers=op)
    assert resp.status_code == 200, resp.text
    assert "Clip" in resp.json()["detail"]
    assert resp.json()["action"]["status"] == "executed"


def test_external_side_effects_are_blocked(client: TestClient, op: dict[str, str]) -> None:
    action_id = _inject(
        client,
        kind=ActionKind.PROPOSE_SOURCE_CHANGE,
        risk=ActionRisk.EXTERNAL,
        status=ActionStatus.APPROVED,  # even approved, external stays out of Stage 1
    )
    resp = client.post(f"/actions/{action_id}/execute", headers=op)
    assert resp.status_code == 409
    assert "external" in resp.json()["error"]["message"].lower()


def test_create_memory_ingests_through_the_pipeline(client: TestClient, op: dict[str, str]) -> None:
    """CREATE_MEMORY remembers an assertion by ingesting it (raw→claims), never a direct write —
    so the remembered fact is grounded evidence, retrievable like any other ingested doc."""
    action_id = _inject(
        client,
        kind=ActionKind.CREATE_MEMORY,
        risk=ActionRisk.MEMORY_WRITE,
        parameters={"content": "Ada Lovelace is the CTO of Acme Inc."},
        status=ActionStatus.APPROVED,
    )
    resp = client.post(f"/actions/{action_id}/execute", headers=op)
    assert resp.status_code == 200, resp.text
    assert resp.json()["doc_id"]
    assert resp.json()["action"]["status"] == "executed"

    answered = client.post("/query", json={"text": "Who is the CTO of Acme?"}, headers=op)
    assert answered.json()["sufficient"] is True  # the assertion is now grounded, citable evidence


def test_create_memory_without_content_is_a_clean_error(
    client: TestClient, op: dict[str, str]
) -> None:
    action_id = _inject(
        client,
        kind=ActionKind.CREATE_MEMORY,
        risk=ActionRisk.MEMORY_WRITE,
        status=ActionStatus.APPROVED,  # approved, but nothing to remember
    )
    resp = client.post(f"/actions/{action_id}/execute", headers=op)
    assert resp.status_code == 409
    assert "content" in resp.json()["error"]["message"]


def test_create_wiki_patch_proposes_for_review(client: TestClient, op: dict[str, str]) -> None:
    """CREATE_WIKI_PATCH queues a patch in the review inbox (never a direct write); the existing
    wiki approval commits it later."""
    action_id = _inject(
        client,
        kind=ActionKind.CREATE_WIKI_PATCH,
        risk=ActionRisk.WIKI_WRITE,
        parameters={"title": "Acme", "body": "Acme ships in 2026."},
        status=ActionStatus.APPROVED,
    )
    resp = client.post(f"/actions/{action_id}/execute", headers=op)
    assert resp.status_code == 200, resp.text
    patch_id = resp.json()["patch_id"]
    assert patch_id
    # the patch is proposed for review, not applied — it shows up in the wiki patch inbox.
    patches = client.get("/wiki/patches", headers=op).json()
    assert any(p["id"] == patch_id and p["status"] == "proposed" for p in patches)


def test_propose_source_change_is_deferred(client: TestClient, op: dict[str, str]) -> None:
    action_id = _inject(
        client,
        kind=ActionKind.PROPOSE_SOURCE_CHANGE,
        risk=ActionRisk.REVERSIBLE,  # not external, so it reaches the (unimplemented) dispatch
        status=ActionStatus.APPROVED,
    )
    resp = client.post(f"/actions/{action_id}/execute", headers=op)
    assert resp.status_code == 409
    assert "not implemented" in resp.json()["error"]["message"].lower()


def test_executing_emits_an_audit_event(client: TestClient, op: dict[str, str]) -> None:
    action = client.post("/actions", json={"command": "anything"}, headers=op).json()
    client.post(f"/actions/{action['id']}/execute", headers=op)
    actions = [e["action"] for e in client.get("/audit", headers=op).json()]
    assert "action.executed" in actions
