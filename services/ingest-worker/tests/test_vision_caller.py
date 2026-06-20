"""The worker assembles a vision caller for OCR only when a vision model is configured."""

from __future__ import annotations

from metis_ingest_worker.app import _vision_caller
from metis_ingest_worker.settings import IngestWorkerSettings
from metis_protocol import AuditEvent


class _Sink:
    async def emit(self, event: AuditEvent) -> None: ...


def test_no_vision_caller_when_unconfigured() -> None:
    settings = IngestWorkerSettings(anthropic_api_key="", vision_endpoint="", vision_model="")
    caller, closers = _vision_caller(settings, _Sink())
    assert caller is None  # no vision model -> no OCR, no crash
    assert closers == []


def test_vision_caller_built_from_an_anthropic_key() -> None:
    settings = IngestWorkerSettings(
        anthropic_api_key="sk-test", vision_endpoint="", vision_model=""
    )
    caller, closers = _vision_caller(settings, _Sink())
    assert caller is not None  # a vision-capable caller is assembled (client constructed, no call)
    assert closers  # the Anthropic client is registered for shutdown
