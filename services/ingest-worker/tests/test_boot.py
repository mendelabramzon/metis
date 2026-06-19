import pytest

from metis_ingest_worker.app import build_connector, run
from metis_ingest_worker.settings import IngestWorkerSettings
from metis_ingestion import ImapConnector, LocalFolderConnector
from metis_protocol import WorkspaceId

_WS = WorkspaceId("ws_" + "1" * 32)


def test_run_dry_run_wires_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METIS_INGEST_WORKER_POLL_INTERVAL_SECONDS", "1.5")
    settings = run(dry_run=True)
    assert settings.service_name == "ingest-worker"
    assert settings.poll_interval_seconds == 1.5  # env overrides the default (ADR 0006)


def test_build_connector_defaults_to_local_folder() -> None:
    connector = build_connector(IngestWorkerSettings(connector="local_folder"), _WS)
    assert isinstance(connector, LocalFolderConnector)


def test_build_connector_selects_imap() -> None:
    settings = IngestWorkerSettings(
        connector="imap", imap_host="mail.example", imap_username="ada", imap_password="secret"
    )
    connector = build_connector(settings, _WS)
    assert isinstance(connector, ImapConnector)  # the live IMAP transport is wired underneath
