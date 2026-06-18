"""Event envelope versioning: every event name resolves to a versioned payload
schema, unknown names are rejected, and build/decode round-trips."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from metis_protocol.errors import ContractViolationError, UnknownEventError
from metis_protocol.events import (
    EVENT_REGISTRY,
    EventName,
    build_envelope,
    decode_payload,
    payload_spec,
)
from metis_protocol.examples import WS, extraction_batch, mem_cell

_WHEN = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_every_event_name_has_a_versioned_payload_spec() -> None:
    for name in EventName:
        spec = payload_spec(name)
        assert spec.event_version >= 1


def test_unknown_event_is_rejected() -> None:
    with pytest.raises(UnknownEventError):
        payload_spec("does.not.exist")  # type: ignore[arg-type]


def test_envelope_build_and_decode_roundtrip() -> None:
    batch = extraction_batch()
    env = build_envelope(
        event_name=EventName.CLAIMS_EXTRACTED,
        payload=batch,
        workspace_id=WS,
        occurred_at=_WHEN,
        trace_id="trace-1",
    )
    assert env.event_version == EVENT_REGISTRY[EventName.CLAIMS_EXTRACTED].event_version
    assert env.payload_schema_version == batch.schema_version
    assert decode_payload(env) == batch


def test_build_envelope_rejects_mismatched_payload() -> None:
    with pytest.raises(ContractViolationError):
        build_envelope(
            event_name=EventName.CLAIMS_EXTRACTED,
            payload=mem_cell(),
            workspace_id=WS,
            occurred_at=_WHEN,
            trace_id="trace-1",
        )
