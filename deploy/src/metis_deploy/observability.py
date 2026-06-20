"""Observability vocabulary: the metrics + trace field an operator inspects.

OpenTelemetry *collection* is configured in ``observability/otel-collector.yml``; the metric
vocabulary and the OTel SDK wiring (instruments, exporters, span helpers) live in
:mod:`metis_core.observability` so every emission seam — the gateway, the workers, the job queue,
the model router — reaches them without crossing a package boundary. This module re-exports that
vocabulary (the deploy package owns the dashboards/alerts that chart it) and the restore-drill emit
helper used by ``backup/restore_drill.py``.
"""

from __future__ import annotations

from metis_core.observability import (
    METRIC_LABELS,
    TRACE_ID_FIELD,
    Metric,
    flush_telemetry,
    incr_restore_drill,
    setup_telemetry,
)

__all__ = [
    "METRIC_LABELS",
    "TRACE_ID_FIELD",
    "Metric",
    "flush_telemetry",
    "incr_restore_drill",
    "setup_telemetry",
]
