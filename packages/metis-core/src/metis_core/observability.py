"""OpenTelemetry emission for the operator dashboards + cross-service traces.

The metric *vocabulary* (what an operator charts) and the OTel SDK wiring live here in the shared
spine so every emission seam — the job queue, the model router, the ingest pipeline, the skill
runner, and the gateway — reaches it without crossing a package boundary (``metis-deploy``
re-exports the vocabulary for its dashboards). Two design rules keep this cheap and safe:

- **Lazy + no-op.** OpenTelemetry is imported only inside :func:`setup_telemetry` and the span
  helpers, and the metric instruments stay empty until a process calls ``setup_telemetry``. So a
  unit test, the CLI, or any process that never opts in pays nothing and needs no collector.
- **Bounded cardinality.** ``METRIC_LABELS`` fixes the allowed label keys per metric (task class /
  provider / connector — never per-artifact / per-claim), matching the collector's drop rules.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from enum import StrEnum
from typing import Any

#: The field that ties a unit of work together across gateway + workers (logs and traces).
TRACE_ID_FIELD = "trace_id"

#: Logical name of the tracer/meter every service shares (resources distinguish the service).
_INSTRUMENTATION_SCOPE = "metis"


class Metric(StrEnum):
    MODEL_COST_USD = "metis.model.cost_usd"  # model spend, by task class
    POLICY_DENIALS = "metis.policy.denials"  # restricted-data / permission denials
    INGESTION_LAG_SECONDS = "metis.ingestion.lag_seconds"  # discover -> evidence latency
    PARSE_FAILURES = "metis.ingestion.parse_failures"  # parse/extraction failure rate
    JOB_FAILURES = "metis.jobs.failures"  # failed background jobs
    SKILL_RUNS = "metis.skills.runs"  # skill executions, by outcome
    RESTORE_DRILL_RUNS = "metis.backup.restore_drill_runs"  # scheduled restore-drill outcomes


#: Allowed label keys per metric — bounded cardinality by construction.
METRIC_LABELS: dict[Metric, tuple[str, ...]] = {
    Metric.MODEL_COST_USD: ("task_class", "provider", "tier"),
    Metric.POLICY_DENIALS: ("kind", "sensitivity"),
    Metric.INGESTION_LAG_SECONDS: ("connector",),
    Metric.PARSE_FAILURES: ("media_type",),
    Metric.JOB_FAILURES: ("kind",),
    Metric.SKILL_RUNS: ("skill", "outcome"),
    Metric.RESTORE_DRILL_RUNS: ("outcome",),
}

# Instruments, populated by setup_telemetry; empty -> every emit helper below is a no-op. Stored as
# ``Any`` so importing this module never imports OpenTelemetry.
_counters: dict[Metric, Any] = {}
_histograms: dict[Metric, Any] = {}
_configured = False


def setup_telemetry(service_name: str, *, endpoint: str | None = None) -> None:
    """Install the OTel meter + tracer providers and build the metric instruments (idempotent).

    Called once per process at startup (the gateway lifespan, each worker's ``run``). With no
    ``endpoint`` (``OTEL_EXPORTER_OTLP_ENDPOINT`` unset) the providers are built without exporters,
    so a dev run with no collector still works and emits nowhere instead of logging connection
    errors. ``service_name`` distinguishes the emitter (gateway / ingest-worker / ...) in the trace.
    """
    global _configured
    if _configured:
        return

    import os

    from opentelemetry import metrics, trace
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    endpoint = endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    resource = Resource.create({SERVICE_NAME: service_name})

    readers = []
    tracer_provider = TracerProvider(resource=resource)
    if endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        readers.append(PeriodicExportingMetricReader(OTLPMetricExporter(insecure=True)))
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(insecure=True)))

    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=readers))
    trace.set_tracer_provider(tracer_provider)
    install_instruments(metrics.get_meter(_INSTRUMENTATION_SCOPE))
    _configured = True


def install_instruments(meter: Any) -> None:
    """Build the metric instruments from ``meter`` (split out so a test can wire an in-memory
    reader's meter without touching the process-global provider)."""
    _counters[Metric.MODEL_COST_USD] = meter.create_counter(Metric.MODEL_COST_USD, unit="usd")
    _counters[Metric.POLICY_DENIALS] = meter.create_counter(Metric.POLICY_DENIALS)
    _counters[Metric.PARSE_FAILURES] = meter.create_counter(Metric.PARSE_FAILURES)
    _counters[Metric.JOB_FAILURES] = meter.create_counter(Metric.JOB_FAILURES)
    _counters[Metric.SKILL_RUNS] = meter.create_counter(Metric.SKILL_RUNS)
    _counters[Metric.RESTORE_DRILL_RUNS] = meter.create_counter(Metric.RESTORE_DRILL_RUNS)
    _histograms[Metric.INGESTION_LAG_SECONDS] = meter.create_histogram(
        Metric.INGESTION_LAG_SECONDS, unit="s"
    )


def _add(metric: Metric, amount: float, labels: Mapping[str, str]) -> None:
    counter = _counters.get(metric)
    if counter is not None:
        counter.add(amount, dict(labels))


def _observe(metric: Metric, value: float, labels: Mapping[str, str]) -> None:
    histogram = _histograms.get(metric)
    if histogram is not None:
        histogram.record(value, dict(labels))


def record_model_cost(cost_usd: float, *, task_class: str, provider: str, tier: str) -> None:
    """Accrue model spend for the spend/budget dashboard (the acceptance-critical signal)."""
    _add(
        Metric.MODEL_COST_USD,
        cost_usd,
        {"task_class": task_class, "provider": provider, "tier": tier},
    )


def incr_policy_denial(*, kind: str, sensitivity: str) -> None:
    """Count an allowlist/permission denial (e.g. restricted data kept off an external provider)."""
    _add(Metric.POLICY_DENIALS, 1, {"kind": kind, "sensitivity": sensitivity})


def observe_ingestion_lag(seconds: float, *, connector: str) -> None:
    """Record how long a connector's sync cycle took (the ingestion-lag signal)."""
    _observe(Metric.INGESTION_LAG_SECONDS, seconds, {"connector": connector})


def incr_parse_failure(*, media_type: str) -> None:
    """Count a parse/extraction failure, by media type."""
    _add(Metric.PARSE_FAILURES, 1, {"media_type": media_type})


def incr_job_failure(*, kind: str) -> None:
    """Count a failed background job, by kind (the connector-failure signal operators watch)."""
    _add(Metric.JOB_FAILURES, 1, {"kind": kind})


def incr_skill_run(*, skill: str, outcome: str) -> None:
    """Count a skill execution, by skill and outcome (success/error/rejected/...)."""
    _add(Metric.SKILL_RUNS, 1, {"skill": skill, "outcome": outcome})


def incr_restore_drill(*, outcome: str) -> None:
    """Count a scheduled restore-drill run; the freshness alert fires when ``pass`` runs stop."""
    _add(Metric.RESTORE_DRILL_RUNS, 1, {"outcome": outcome})


def flush_telemetry(timeout_millis: int = 5000) -> None:
    """Force-flush pending metrics + spans. A short-lived batch process (the restore drill, a
    backup) must call this before it exits, else its emissions drop before the exporter fires.
    """
    from opentelemetry import metrics, trace

    meter_provider = metrics.get_meter_provider()
    if hasattr(meter_provider, "force_flush"):
        meter_provider.force_flush(timeout_millis)
    tracer_provider = trace.get_tracer_provider()
    if hasattr(tracer_provider, "force_flush"):
        tracer_provider.force_flush(timeout_millis)


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    """A traced unit of work (a no-op span until ``setup_telemetry`` installs a tracer provider)."""
    from opentelemetry import trace

    tracer = trace.get_tracer(_INSTRUMENTATION_SCOPE)
    with tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            current.set_attribute(key, value)
        yield current


def current_trace_carrier() -> dict[str, str]:
    """W3C ``traceparent`` headers for the active span, to stash on a job so a worker can resume the
    trace. Empty when no span is active (then the worker simply starts a fresh trace)."""
    from opentelemetry.propagate import inject

    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier


@contextmanager
def linked_span(name: str, carrier: Mapping[str, str], **attributes: Any) -> Iterator[Any]:
    """Open a span as a child of the context carried in ``carrier`` (the enqueuer's trace), linking
    a worker's execution back to the gateway request that scheduled it."""
    from opentelemetry import trace
    from opentelemetry.propagate import extract

    parent = extract(dict(carrier))
    tracer = trace.get_tracer(_INSTRUMENTATION_SCOPE)
    with tracer.start_as_current_span(name, context=parent) as current:
        for key, value in attributes.items():
            current.set_attribute(key, value)
        yield current
