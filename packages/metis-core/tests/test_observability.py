"""Telemetry: the emit helpers feed the cataloged instruments, the model router emits a policy
denial when the allowlist suppresses an external provider, and a job's trace carrier links a
worker's span back to the gateway request that scheduled it (gateway -> worker -> store)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from metis_core import observability
from metis_core.llm import AnthropicProvider, MetisModelRouter, StubProvider
from metis_core.observability import Metric
from metis_protocol import ModelRequest, ModelTaskClass, Sensitivity


@pytest.fixture
def reader() -> Iterator[InMemoryMetricReader]:
    """Wire the emit helpers to an in-memory reader's meter (no process-global provider, restored
    afterwards) so a test can read exactly what was emitted."""
    saved_counters = dict(observability._counters)
    saved_histograms = dict(observability._histograms)
    in_memory = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[in_memory])
    observability.install_instruments(provider.get_meter("metis"))
    try:
        yield in_memory
    finally:
        observability._counters.clear()
        observability._counters.update(saved_counters)
        observability._histograms.clear()
        observability._histograms.update(saved_histograms)


def _points(reader: InMemoryMetricReader, metric: Metric) -> list[Any]:
    data = reader.get_metrics_data()
    points: list[Any] = []
    if data is None:  # nothing recorded against this reader yet
        return points
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for entry in scope_metric.metrics:
                if entry.name == metric.value:
                    points.extend(entry.data.data_points)
    return points


def _request(task: ModelTaskClass, sensitivity: Sensitivity) -> ModelRequest:
    return ModelRequest(task_class=task, messages=(), sensitivity=sensitivity)


def test_job_failure_counts_by_kind(reader: InMemoryMetricReader) -> None:
    observability.incr_job_failure(kind="ingest.poll")
    points = _points(reader, Metric.JOB_FAILURES)
    assert len(points) == 1
    assert points[0].value == 1
    assert points[0].attributes["kind"] == "ingest.poll"


def test_model_cost_accrues_by_task_and_provider(reader: InMemoryMetricReader) -> None:
    observability.record_model_cost(
        0.5, task_class="query_answer", provider="anthropic", tier="frontier"
    )
    observability.record_model_cost(
        0.25, task_class="query_answer", provider="anthropic", tier="frontier"
    )
    points = _points(reader, Metric.MODEL_COST_USD)
    assert sum(point.value for point in points) == pytest.approx(0.75)
    assert points[0].attributes == {
        "task_class": "query_answer",
        "provider": "anthropic",
        "tier": "frontier",
    }


def test_ingestion_lag_is_a_histogram(reader: InMemoryMetricReader) -> None:
    observability.observe_ingestion_lag(2.5, connector="imap")
    points = _points(reader, Metric.INGESTION_LAG_SECONDS)
    assert len(points) == 1
    assert points[0].count == 1
    assert points[0].sum == pytest.approx(2.5)
    assert points[0].attributes["connector"] == "imap"


def test_parse_and_skill_helpers_emit(reader: InMemoryMetricReader) -> None:
    observability.incr_parse_failure(media_type="application/pdf")
    observability.incr_skill_run(skill="web_search", outcome="success")
    assert _points(reader, Metric.PARSE_FAILURES)[0].attributes["media_type"] == "application/pdf"
    skill = _points(reader, Metric.SKILL_RUNS)[0]
    assert skill.attributes == {"skill": "web_search", "outcome": "success"}


def test_router_emits_a_denial_when_external_is_suppressed(reader: InMemoryMetricReader) -> None:
    # Cloud preferred, local fallback: restricted data suppresses the external provider -> a denial.
    router = MetisModelRouter([AnthropicProvider(client=None, name="anthropic"), StubProvider()])
    router.route(_request(ModelTaskClass.EXTRACT_CLAIMS, Sensitivity.RESTRICTED))
    points = _points(reader, Metric.POLICY_DENIALS)
    assert len(points) == 1
    assert points[0].attributes == {"kind": "external_provider", "sensitivity": "restricted"}


def test_router_does_not_deny_internal_data(reader: InMemoryMetricReader) -> None:
    router = MetisModelRouter([AnthropicProvider(client=None, name="anthropic"), StubProvider()])
    router.route(_request(ModelTaskClass.EXTRACT_CLAIMS, Sensitivity.INTERNAL))
    assert _points(reader, Metric.POLICY_DENIALS) == []


def test_emit_is_a_noop_without_instruments() -> None:
    # No reader fixture: the instruments dict is empty, so a stray emit never raises.
    observability._counters.clear()
    observability._histograms.clear()
    observability.incr_job_failure(kind="x")  # must not raise


def test_job_trace_carrier_links_worker_span_to_gateway_span() -> None:
    observability.setup_telemetry("test-gateway")  # a real (non-noop) tracer provider
    with observability.span("http.request") as gateway_span:
        carrier = observability.current_trace_carrier()
        gateway_trace_id = gateway_span.get_span_context().trace_id
    assert carrier  # a non-empty W3C traceparent the job would carry

    with observability.linked_span("ingest.sync", carrier) as worker_span:
        worker_ctx = worker_span.get_span_context()
        assert worker_ctx.trace_id == gateway_trace_id  # same trace across the queue hop
        assert worker_ctx.span_id != gateway_span.get_span_context().span_id  # a child span


def test_empty_carrier_starts_a_fresh_trace() -> None:
    observability.setup_telemetry("test-gateway")
    with observability.linked_span("ingest.sync", {}) as worker_span:
        assert worker_span.get_span_context().trace_id != 0  # a valid fresh trace, not a no-op
