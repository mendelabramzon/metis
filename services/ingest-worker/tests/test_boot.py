import pytest

from metis_ingest_worker.app import run


def test_run_dry_run_wires_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METIS_INGEST_WORKER_POLL_INTERVAL_SECONDS", "1.5")
    settings = run(dry_run=True)
    assert settings.service_name == "ingest-worker"
    assert settings.poll_interval_seconds == 1.5  # env overrides the default (ADR 0006)
