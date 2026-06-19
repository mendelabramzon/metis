"""Evidence drill-down: from a citation back to the claim, its quoted spans, and the artifact.

The in-memory cases cover the HTTP contract + isolation; the Postgres case proves the quote is
sliced from the stored document and the consolidated memory cell resolves to its claims.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.models import MemCellRow
from metis_gateway.app import create_app
from metis_gateway.settings import GatewaySettings

_NOTE = "Ada Lovelace leads the Apollo project."


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


def _ingest_and_cite(client: TestClient, ws: str, headers: dict[str, str]) -> dict[str, str]:
    """Ingest the note into ``ws``, query it, and return the first citation (claim + artifact)."""
    ingest = client.post(
        f"/workspaces/{ws}/ingest", json={"filename": "note.md", "content": _NOTE}, headers=headers
    )
    assert ingest.status_code == 202, ingest.text
    answer = client.post(f"/workspaces/{ws}/query", json={"text": "Apollo"}, headers=headers)
    assert answer.status_code == 200, answer.text
    citations = answer.json()["citations"]
    assert citations, answer.text
    return citations[0]


def test_claim_drilldown_returns_quoted_spans(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]

    citation = _ingest_and_cite(client, ada_ws, _bearer(ada))

    claim = client.get(f"/workspaces/{ada_ws}/claims/{citation['claim_id']}", headers=_bearer(ada))
    assert claim.status_code == 200, claim.text
    body = claim.json()
    assert body["text"]
    assert body["spans"], "a claim cites at least one span"
    span = body["spans"][0]
    assert span["artifact_id"] == citation["artifact_id"]
    assert span["quote"]  # the exact source text, sliced from the doc
    assert span["quote"] in _NOTE


def test_artifact_drilldown_returns_source_metadata(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]
    citation = _ingest_and_cite(client, ada_ws, _bearer(ada))

    artifact = client.get(
        f"/workspaces/{ada_ws}/artifacts/{citation['artifact_id']}", headers=_bearer(ada)
    )
    assert artifact.status_code == 200, artifact.text
    body = artifact.json()
    assert body["filename"] == "note.md"
    assert body["connector"] == "gateway"
    assert body["tombstoned"] is False


def test_evidence_is_member_gated_and_404s_unknown(client: TestClient, op: dict[str, str]) -> None:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    ada = _provision(client, op, org_id, "ada@acme.example")
    grace = _provision(client, op, org_id, "grace@acme.example")
    ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]
    citation = _ingest_and_cite(client, ada_ws, _bearer(ada))

    # A non-member cannot read Ada's evidence — the isolation gate denies before any lookup.
    blocked = client.get(
        f"/workspaces/{ada_ws}/claims/{citation['claim_id']}", headers=_bearer(grace)
    )
    assert blocked.status_code == 403

    # Unknown ids in the caller's own workspace are 404s.
    assert (
        client.get(f"/workspaces/{ada_ws}/claims/clm_{'0' * 32}", headers=_bearer(ada)).status_code
        == 404
    )
    assert (
        client.get(f"/workspaces/{ada_ws}/memory/mc_{'0' * 32}", headers=_bearer(ada)).status_code
        == 404
    )


def _first_mem_cell_id(sessionmaker: async_sessionmaker[AsyncSession], workspace_id: str) -> str:
    async def _query() -> str:
        async with sessionmaker() as session:
            cell_id = (
                await session.scalars(
                    select(MemCellRow.id).where(MemCellRow.workspace_id == workspace_id)
                )
            ).first()
        assert cell_id is not None, "ingestion consolidates claims into a mem cell"
        return cell_id

    return asyncio.run(_query())


def test_evidence_drilldown_durable(
    pg_settings: GatewaySettings, pg_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    op = {"Authorization": "Bearer op-token"}
    with TestClient(create_app(pg_settings)) as client:
        org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
        # Gateway Postgres fixtures share one DB across tests; use an email unique to this test.
        ada = _provision(client, op, org_id, "ada-evidence@acme.example")
        ada_ws = client.get("/workspaces", headers=_bearer(ada)).json()[0]["id"]
        citation = _ingest_and_cite(client, ada_ws, _bearer(ada))

        # The quote is sliced from the stored normalized doc.
        claim = client.get(
            f"/workspaces/{ada_ws}/claims/{citation['claim_id']}", headers=_bearer(ada)
        ).json()
        assert claim["spans"]
        assert claim["spans"][0]["quote"] in _NOTE

        artifact = client.get(
            f"/workspaces/{ada_ws}/artifacts/{citation['artifact_id']}", headers=_bearer(ada)
        ).json()
        assert artifact["filename"] == "note.md"

        # The consolidated memory cell resolves back to its claims.
        cell_id = _first_mem_cell_id(pg_sessionmaker, ada_ws)
        cell = client.get(f"/workspaces/{ada_ws}/memory/{cell_id}", headers=_bearer(ada))
        assert cell.status_code == 200, cell.text
        assert cell.json()["claim_ids"]
