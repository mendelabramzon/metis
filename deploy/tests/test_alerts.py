"""alerts.yml is a well-formed Prometheus rule file whose rules reference metrics we actually emit,
so an alert can never silently watch a metric that has been renamed or removed."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from metis_deploy.observability import Metric

ALERTS = Path(__file__).resolve().parents[1] / "observability" / "alerts.yml"


def _prometheus_name(metric: Metric) -> str:
    # The collector exports OTel names with dots -> underscores and no suffixes
    # (add_metric_suffixes: false), so metis.model.cost_usd scrapes as metis_model_cost_usd.
    return metric.value.replace(".", "_")


def _rules() -> list[dict[str, Any]]:
    doc = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))
    rules: list[dict[str, Any]] = []
    for group in doc["groups"]:
        rules.extend(group["rules"])
    return rules


def test_alerts_is_a_well_formed_rule_file() -> None:
    doc = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))
    assert isinstance(doc["groups"], list)
    assert doc["groups"]
    for group in doc["groups"]:
        assert group["name"]
        assert group["rules"]


def test_every_rule_has_the_required_fields() -> None:
    for rule in _rules():
        assert rule["alert"]
        assert rule["expr"]
        assert rule["labels"]["severity"] in {"info", "warning", "critical"}
        assert rule["annotations"]["summary"]
        assert rule["annotations"]["description"]


def test_every_rule_references_an_emitted_metric() -> None:
    names = {_prometheus_name(metric) for metric in Metric}
    for rule in _rules():
        assert any(name in rule["expr"] for name in names), (
            f"{rule['alert']} references no known metric"
        )


def test_the_roadmap_alerts_are_present() -> None:
    # spend ceiling, job-failure rate, ingestion-lag, restore-drill freshness (the roadmap's four).
    alerts = {rule["alert"] for rule in _rules()}
    expected = {"ModelSpendCeiling", "JobFailuresHigh", "IngestionLagHigh", "RestoreDrillStale"}
    assert expected <= alerts


def test_promtool_validates_the_rules_if_available() -> None:
    promtool = shutil.which("promtool")
    if promtool is None:
        pytest.skip("promtool not installed")
    result = subprocess.run(
        [promtool, "check", "rules", str(ALERTS)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
