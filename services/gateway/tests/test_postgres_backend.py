"""The Postgres backend persists evidence: ingest survives a fresh app over the same database."""

from __future__ import annotations

from fastapi.testclient import TestClient

from metis_gateway.app import create_app
from metis_gateway.settings import GatewaySettings

_OP = {"Authorization": "Bearer op-token"}
_USER = {"Authorization": "Bearer user-token"}
_DOC = "Ada Lovelace is the CTO of Acme. Acme was founded in 2019."
_Q = {"text": "Who is the CTO of Acme?"}


def test_ingest_persists_and_survives_a_restart(pg_settings: GatewaySettings) -> None:
    # First app: ingest a document and confirm a cited answer comes back from the Postgres stores.
    with TestClient(create_app(pg_settings)) as first:
        source_id = first.post(
            "/sources",
            json={"name": "docs", "connector": "web_clip", "sensitivity": "internal"},
            headers=_OP,
        ).json()["id"]
        ingested = first.post(
            f"/sources/{source_id}/ingest",
            json={"filename": "acme.txt", "content": _DOC},
            headers=_OP,
        )
        assert ingested.status_code == 202
        assert ingested.json()["claims"] >= 1

        answered = first.post("/query", json=_Q, headers=_USER).json()
        assert answered["sufficient"] is True
        assert "Ada" in answered["answer"]
        assert answered["citations"]
        assert answered["citations"][0]["source_span_id"]  # resolved from the claim store

        # the audit trail is read back from Postgres
        audit = first.get("/audit", headers=_OP).json()
        assert any(event["action"] == "agent.run.finished" for event in audit)

    # Second app over the SAME database, no re-ingest: the evidence persisted.
    with TestClient(create_app(pg_settings)) as second:
        again = second.post("/query", json=_Q, headers=_USER).json()
        assert again["sufficient"] is True
        assert "Ada" in again["answer"]
