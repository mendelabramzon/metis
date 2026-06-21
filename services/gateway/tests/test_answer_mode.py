"""The query response reports whether a model produced the answer (I2a).

With no chat provider configured, answers fall back to deterministic extractive text — the user's
"asking goes without an LLM" case — and the response says so via ``answer_mode``, so the UI can
surface it rather than silently passing extractive text off as a model answer.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from metis_core.llm import MetisModelRouter, ModelCaller, StubProvider
from metis_gateway.backend import InMemoryWorkspace, RecordingAuditSink
from metis_protocol import WorkspaceId


def _bearer(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_id}"}


def _ada_workspace(client: TestClient, op: dict[str, str]) -> tuple[dict[str, str], str]:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = client.post(
        "/users",
        json={"organization_id": org_id, "email": "ada@acme.example", "display_name": "Ada"},
        headers=op,
    ).json()["id"]
    ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]
    return _bearer(ada), ws


def test_query_without_provider_is_extractive(client: TestClient, op: dict[str, str]) -> None:
    ada, ws = _ada_workspace(client, op)
    client.post(
        f"/workspaces/{ws}/upload",
        files=[("files", ("acme.txt", b"Ada Lovelace is the CTO of Acme Inc."))],
        headers=ada,
    )
    answered = client.post(
        f"/workspaces/{ws}/query", json={"text": "Who is the CTO of Acme?"}, headers=ada
    ).json()
    assert answered["sufficient"] is True
    assert answered["answer_mode"] == "extractive"  # no provider wired in the test deployment


def test_answers_with_model_reflects_the_wired_caller() -> None:
    ws_id = WorkspaceId("ws_" + "3" * 32)
    assert InMemoryWorkspace(ws_id).answers_with_model is False  # no caller => extractive
    caller = ModelCaller(MetisModelRouter([StubProvider()]), RecordingAuditSink())
    assert InMemoryWorkspace(ws_id, caller=caller).answers_with_model is True
