import pytest

from metis_gateway.app import run


def test_run_dry_run_wires_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METIS_GATEWAY_PORT", "9999")
    settings = run(dry_run=True)
    assert settings.service_name == "gateway"
    assert settings.port == 9999  # process env overrides the default (ADR 0006)
