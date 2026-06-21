import pytest

from metis_runtime_worker.app import run


def test_run_dry_run_wires_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METIS_RUNTIME_WORKER_POLL_INTERVAL_SECONDS", "0.5")
    monkeypatch.setenv(
        "METIS_RUNTIME_WORKER_DATABASE_URL", "postgresql+asyncpg://metis:metis@db:5432/metis"
    )
    settings = run(
        dry_run=True
    )  # wires the RuntimeWorker; the async engine is lazy (no connection)
    assert settings.service_name == "runtime-worker"
    assert settings.poll_interval_seconds == 0.5  # env overrides the default (ADR 0006)
    assert settings.database_url.endswith("@db:5432/metis")
