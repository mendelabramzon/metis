"""Observability vocabulary: the metrics + trace field an operator inspects.

OpenTelemetry *collection* is configured in ``observability/otel-collector.yml``; this is the
Python-side catalog of what the dashboards chart and what stitches a unit of work across services.
The acceptance bar is that an operator can inspect failed jobs, model spend, policy denials, and
ingestion lag — so those are first-class metrics here. Label sets are deliberately bounded (task
class / provider / connector — never per-artifact / per-claim) to avoid a cardinality blow-up.
"""

from __future__ import annotations

from enum import StrEnum

#: The field that ties a unit of work together across gateway + workers (logs and traces).
TRACE_ID_FIELD = "trace_id"


class Metric(StrEnum):
    MODEL_COST_USD = "metis.model.cost_usd"  # model spend, by task class
    POLICY_DENIALS = "metis.policy.denials"  # restricted-data / permission denials
    INGESTION_LAG_SECONDS = "metis.ingestion.lag_seconds"  # discover -> evidence latency
    PARSE_FAILURES = "metis.ingestion.parse_failures"  # parse/extraction failure rate
    JOB_FAILURES = "metis.jobs.failures"  # failed background jobs
    SKILL_RUNS = "metis.skills.runs"  # skill executions, by outcome


#: Allowed label keys per metric — bounded cardinality by construction.
METRIC_LABELS: dict[Metric, tuple[str, ...]] = {
    Metric.MODEL_COST_USD: ("task_class", "provider", "tier"),
    Metric.POLICY_DENIALS: ("kind", "sensitivity"),
    Metric.INGESTION_LAG_SECONDS: ("connector",),
    Metric.PARSE_FAILURES: ("media_type",),
    Metric.JOB_FAILURES: ("kind",),
    Metric.SKILL_RUNS: ("skill", "outcome"),
}
