"""Creating a Telegram source carries + validates its per-chat config (Business connection + chat),
so a misconfigured source is rejected at the gateway; a valid one queues a sync like any other."""

from __future__ import annotations

_VALID = {"business_connection_id": "bc-1", "chat_id": 7001, "chat_type": "private"}


def _create(client, op, config):
    return client.post(
        "/sources",
        json={
            "name": "ada-dm",
            "connector": "telegram",
            "sensitivity": "confidential",
            "config": config,
        },
        headers=op,
    )


def test_create_telegram_source_with_valid_config(client, op) -> None:
    resp = _create(client, op, _VALID)
    assert resp.status_code == 201, resp.text
    assert resp.json()["connector"] == "telegram"


def test_create_telegram_source_rejects_missing_chat(client, op) -> None:
    resp = _create(client, op, {"business_connection_id": "bc-1"})  # no chat_id
    assert resp.status_code == 409, resp.text


def test_telegram_source_syncs_via_a_queued_job(client, op) -> None:
    source_id = _create(client, op, _VALID).json()["id"]
    resp = client.post(f"/sources/{source_id}/sync", headers=op)
    assert resp.status_code == 202, resp.text
    assert resp.json()["job_id"]
