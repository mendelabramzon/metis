"""Inbound webhook signatures are verified (valid / wrong-secret / tampered / stale), and an
unverified payload never becomes a job."""

from __future__ import annotations

import pytest

from metis_ingestion.connectors import WebhookVerificationError, build_webhook_job
from metis_ingestion.security import sign, verify_webhook
from metis_protocol import WorkspaceId

_WS = WorkspaceId(f"ws_{'f' * 32}")


def test_valid_signature_passes() -> None:
    sig = sign("shh", body=b'{"event":"x"}', timestamp="1000")
    assert verify_webhook(
        secret="shh", body=b'{"event":"x"}', timestamp="1000", signature=sig, now=1100
    )


def test_wrong_secret_fails() -> None:
    sig = sign("shh", body=b"{}", timestamp="1000")
    assert not verify_webhook(secret="nope", body=b"{}", timestamp="1000", signature=sig, now=1100)


def test_tampered_body_fails() -> None:
    sig = sign("shh", body=b"{}", timestamp="1000")
    assert not verify_webhook(
        secret="shh", body=b'{"evil":1}', timestamp="1000", signature=sig, now=1100
    )


def test_stale_timestamp_is_rejected() -> None:
    sig = sign("shh", body=b"{}", timestamp="1000")
    assert not verify_webhook(
        secret="shh", body=b"{}", timestamp="1000", signature=sig, now=100_000
    )


def test_unverified_payload_is_not_enqueued() -> None:
    # ties to Stage 11: an unverified webhook never becomes an ingest job
    with pytest.raises(WebhookVerificationError):
        build_webhook_job(workspace_id=_WS, connector="slack", event={}, verified=False)
