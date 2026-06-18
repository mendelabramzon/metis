import pytest

from metis_maintainer_worker.app import run


def test_run_dry_run_wires_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METIS_MAINTAINER_WORKER_POLL_INTERVAL_SECONDS", "12")
    settings = run(dry_run=True)
    assert settings.service_name == "maintainer-worker"
    assert settings.poll_interval_seconds == 12  # env overrides the default (ADR 0006)
