"""The Telegram overlay wires the TDLib path correctly (Docker-free structural check).

A live bring-up is a manual smoke (it needs the libtdjson build); this validates the manifest an
operator would run: the bot + TDLib workers and the libtdjson builder are present, the gateway and
the TDLib worker *share* the data volume (so the worker reopens the database the gateway login
created) and both load libtdjson from the lib volume, and the worker runs the telegram_tdlib mode.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_DEPLOY = Path(__file__).resolve().parents[1]
_TDLIB_DATA_ROOT = "/var/lib/metis/tdlib"
_TDLIB_LIB = "/opt/tdlib/libtdjson.so"


def _load(relative: str) -> dict:
    return yaml.safe_load((_DEPLOY / relative).read_text(encoding="utf-8"))


def _mounts(service: dict) -> dict[str, str]:
    """volume_name -> container path, for the service's named-volume mounts."""
    return dict(m.split(":")[:2] for m in service.get("volumes", []))


def test_overlay_defines_the_telegram_services_and_volumes() -> None:
    overlay = _load("compose/profiles.telegram.yml")
    assert {"tdlib-lib", "telegram-bot-worker", "telegram-tdlib-worker"} <= set(overlay["services"])
    assert {"tdliblib", "tdlibdata"} <= set(overlay["volumes"])


def test_gateway_and_worker_share_the_tdlib_data_volume() -> None:
    services = _load("compose/profiles.telegram.yml")["services"]
    gateway = _mounts(services["gateway"])
    worker = _mounts(services["telegram-tdlib-worker"])
    # The load-bearing property: both mount the SAME data volume at the SAME path, so the worker
    # reopens the per-account database the gateway login authorized.
    assert gateway["tdlibdata"] == _TDLIB_DATA_ROOT
    assert worker["tdlibdata"] == _TDLIB_DATA_ROOT
    # ...and both load libtdjson from the shared lib volume.
    assert gateway["tdliblib"] == "/opt/tdlib"
    assert worker["tdliblib"] == "/opt/tdlib"


def test_tdlib_worker_runs_the_backfill_mode_against_the_built_library() -> None:
    worker = _load("compose/profiles.telegram.yml")["services"]["telegram-tdlib-worker"]
    env = worker["environment"]
    assert env["METIS_INGEST_WORKER_MODE"] == "telegram_tdlib"
    assert env["METIS_INGEST_WORKER_TELEGRAM_TDLIB_LIBRARY"] == _TDLIB_LIB
    assert env["METIS_INGEST_WORKER_TELEGRAM_TDLIB_DATA_ROOT"] == _TDLIB_DATA_ROOT
    # it waits for the one-shot libtdjson build before starting
    assert worker["depends_on"]["tdlib-lib"]["condition"] == "service_completed_successfully"


def test_gateway_connect_endpoint_is_configured() -> None:
    gateway = _load("compose/profiles.telegram.yml")["services"]["gateway"]
    env = gateway["environment"]
    assert env["METIS_GATEWAY_TELEGRAM_TDLIB_LIBRARY"] == _TDLIB_LIB
    assert env["METIS_GATEWAY_TELEGRAM_TDLIB_DATA_ROOT"] == _TDLIB_DATA_ROOT
    assert gateway["depends_on"]["tdlib-lib"]["condition"] == "service_completed_successfully"


def test_tdlib_builder_dockerfile_present() -> None:
    assert (_DEPLOY / "images" / "tdlib.Dockerfile").is_file()
