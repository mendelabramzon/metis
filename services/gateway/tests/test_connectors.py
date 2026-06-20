"""The connector catalog (GET /sources/connectors) the source-setup form is built from.

It projects the connector registry: each connector's name, how it authenticates (so the UI runs the
OAuth connect flow for an oauth2 connector first), its default-sensitivity floor, and whether it
validates a connector-specific config payload.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_catalog_projects_the_connector_registry(client: TestClient, op: dict[str, str]) -> None:
    resp = client.get("/sources/connectors", headers=op)
    assert resp.status_code == 200, resp.text
    by_name = {c["name"]: c for c in resp.json()}

    # The Telegram connector needs a token + a per-chat config payload and floors at CONFIDENTIAL.
    assert by_name["telegram"]["auth_method"] == "token"
    assert by_name["telegram"]["requires_config"] is True
    assert by_name["telegram"]["default_sensitivity"] == "confidential"

    # Gmail/Drive are OAuth (so the form offers a Google connect); IMAP is basic auth.
    assert by_name["gmail"]["auth_method"] == "oauth2"
    assert by_name["gdrive"]["auth_method"] == "oauth2"
    assert by_name["imap"]["auth_method"] == "basic"
    # A connector with no config schema reports it (the form sends an empty config).
    assert by_name["imap"]["requires_config"] is False


def test_catalog_requires_authentication(client: TestClient) -> None:
    assert client.get("/sources/connectors").status_code == 401


def test_a_telegram_source_created_from_catalog_config_validates(
    client: TestClient, op: dict[str, str]
) -> None:
    """The shape the console prefills for a discovered chat is accepted by source creation."""
    resp = client.post(
        "/sources",
        json={
            "name": "Acme DM",
            "connector": "telegram",
            "sensitivity": "confidential",
            "config": {
                "business_connection_id": "bizconn-1",
                "chat_id": 4242,
                "chat_type": "private",
            },
        },
        headers=op,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["connector"] == "telegram"
