"""Operator runtime config (I2c/I3b): set provider keys + connector auth without a redeploy.

GET reports effective config (secrets masked) + readiness; PUT persists overrides and applies them
to the live backend by rebuilding the chat plane + OAuth wiring in place. Operator-gated; disabled
(PUT 409s) when no credential-store key is set.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from metis_core.security import generate_key
from metis_gateway.app import create_app
from metis_gateway.settings import GatewaySettings

_OP = {"Authorization": "Bearer op-token"}
_USER = {"Authorization": "Bearer user-token"}
_LOCAL = "http://localhost:11434"


@pytest.fixture
def cfg_client() -> Iterator[TestClient]:
    """An in-memory gateway with a credential-store key, so runtime config is enabled."""
    settings = GatewaySettings(
        operator_token="op-token",
        user_token="user-token",
        workspace_id="ws_" + "9" * 32,
        cred_store_key=generate_key(),
    )
    with TestClient(create_app(settings)) as client:
        yield client


def test_get_reports_status_and_requires_operator(client: TestClient) -> None:
    body = client.get("/admin/config", headers=_OP)
    assert body.status_code == 200, body.text
    payload = body.json()
    assert payload["status"]["chat_provider"] is None  # nothing wired in the default test client
    assert payload["status"]["runtime_config_enabled"] is False  # no cred-store key here
    assert {f["key"] for f in payload["fields"]} >= {"anthropic_api_key", "google_client_id"}
    # Operator-gated.
    assert client.get("/admin/config", headers=_USER).status_code == 403


def test_put_without_cred_store_key_is_409(client: TestClient) -> None:
    blocked = client.put("/admin/config", json={"values": {"model_endpoint": _LOCAL}}, headers=_OP)
    assert blocked.status_code == 409  # runtime config needs a credential-store key


def test_put_wires_a_chat_provider_live(cfg_client: TestClient) -> None:
    backend = cfg_client.app.state.backend  # type: ignore[attr-defined]
    assert backend.model_caller is None  # extractive before any provider is set

    put = cfg_client.put("/admin/config", json={"values": {"model_endpoint": _LOCAL}}, headers=_OP)
    assert put.status_code == 200, put.text
    assert put.json()["status"]["chat_provider"] == "local"
    assert backend.model_caller is not None  # the live plane was rebuilt in place — no restart

    # Persisted: a fresh read still reports it.
    assert cfg_client.get("/admin/config", headers=_OP).json()["status"]["chat_provider"] == "local"

    # Clearing the override removes the provider again, live.
    cleared = cfg_client.put("/admin/config", json={"values": {"model_endpoint": ""}}, headers=_OP)
    assert cleared.json()["status"]["chat_provider"] is None
    assert backend.model_caller is None


def test_put_masks_secrets_and_enables_oauth(cfg_client: TestClient) -> None:
    put = cfg_client.put(
        "/admin/config",
        json={"values": {"google_client_id": "cid-123", "google_client_secret": "super-secret"}},
        headers=_OP,
    )
    assert put.status_code == 200, put.text
    assert put.json()["status"]["google_oauth_configured"] is True

    fields = {f["key"]: f for f in cfg_client.get("/admin/config", headers=_OP).json()["fields"]}
    assert fields["google_client_id"]["value"] == "cid-123"  # non-secret shown
    secret = fields["google_client_secret"]
    assert secret["set"] is True
    assert secret["secret"] is True
    assert secret["value"] == "····cret"  # masked to the last 4
    assert "super" not in (secret["value"] or "")

    # The OAuth connectors now report available in the catalog (no more broken Connect button).
    catalog = {c["name"]: c for c in cfg_client.get("/sources/connectors", headers=_OP).json()}
    assert catalog["gdrive"]["available"] is True
    assert catalog["imap"]["available"] is True  # per-source creds, always available


def test_put_rejects_unknown_key(cfg_client: TestClient) -> None:
    bad = cfg_client.put("/admin/config", json={"values": {"not_a_field": "x"}}, headers=_OP)
    assert bad.status_code == 409


def test_oauth_connectors_unavailable_without_google(client: TestClient) -> None:
    catalog = {c["name"]: c for c in client.get("/sources/connectors", headers=_OP).json()}
    assert catalog["gdrive"]["available"] is False
    assert catalog["gdrive"]["unavailable_reason"]
    assert catalog["web_clip"]["available"] is True  # no-auth connector stays available
