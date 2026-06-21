"""A clean machine can start the stack: the Compose manifest is complete and correctly ordered.

A live `docker compose up` is an operator/manual smoke (it needs Docker + image builds); this
validates, Docker-free, that the manifest a clean machine would run is complete — every service
present, dependencies healthchecked, migrations a one-shot init step the app services wait on, and
the build/env files in place.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_DEPLOY = Path(__file__).resolve().parents[1]

_REQUIRED_SERVICES = {
    "postgres",
    "minio",
    "migrate",
    "gateway",
    "ingest-worker",
    "maintainer-worker",
    "runtime-worker",
    "otel-collector",
}
_APP_SERVICES = {"gateway", "ingest-worker", "maintainer-worker", "runtime-worker"}


def _load(relative: str) -> dict:
    return yaml.safe_load((_DEPLOY / relative).read_text(encoding="utf-8"))


def test_all_required_services_are_defined() -> None:
    services = _load("docker-compose.yml")["services"]
    assert set(services) >= _REQUIRED_SERVICES


def test_dependencies_have_healthchecks() -> None:
    services = _load("docker-compose.yml")["services"]
    for name in ("postgres", "minio", "gateway"):
        assert "healthcheck" in services[name], name


def test_app_services_wait_for_migrations_and_dependencies() -> None:
    services = _load("docker-compose.yml")["services"]
    for name in _APP_SERVICES:
        depends_on = services[name]["depends_on"]
        assert depends_on["migrate"]["condition"] == "service_completed_successfully", name
        assert depends_on["postgres"]["condition"] == "service_healthy", name


def test_migrations_run_once_as_an_init_step() -> None:
    migrate = _load("docker-compose.yml")["services"]["migrate"]
    assert migrate.get("restart", "no") == "no"  # one-shot, not a long-running service
    assert "postgres" in migrate["depends_on"]


def test_dockerfiles_and_entrypoints_present() -> None:
    for service in ("gateway", "ingest-worker", "maintainer-worker", "runtime-worker"):
        assert (_DEPLOY / "images" / f"{service}.Dockerfile").is_file()
    assert (_DEPLOY / "env" / ".env.example").is_file()
    assert (_DEPLOY / "migrate" / "entrypoint.sh").is_file()
    assert (_DEPLOY / "runbook.md").is_file()


def test_gateway_binds_all_interfaces() -> None:
    # 127.0.0.1 (the default) is unreachable through the published port; it must bind 0.0.0.0.
    gateway = _load("docker-compose.yml")["services"]["gateway"]
    assert gateway["environment"]["METIS_GATEWAY_HOST"] == "0.0.0.0"


def test_maintainer_worker_points_at_the_stack_postgres() -> None:
    # The maintainer worker reads its own settings prefix (not METIS_CORE_*), so its DB url must be
    # set explicitly to the stack's Postgres host rather than the localhost default.
    env = _load("docker-compose.yml")["services"]["maintainer-worker"]["environment"]
    assert "postgres:5432" in env["METIS_MAINTAINER_WORKER_DATABASE_URL"]


def test_app_env_disables_arm_crypto_extensions() -> None:
    # OPENSSL_armcap avoids a cryptography SIGILL on virtualized ARM (e.g. Docker Desktop on Apple
    # Silicon); without it every service that touches secrets/auth crashes on startup.
    app_env = _load("docker-compose.yml")["x-app-env"]
    assert "OPENSSL_armcap" in app_env


def test_profiles_select_a_model_runtime() -> None:
    local = _load("compose/profiles.local.yml")["services"]
    gpu = _load("compose/profiles.gpu.yml")["services"]
    cloud = _load("compose/profiles.cloud.yml")["services"]
    assert "model-runtime" in local  # local: CPU Ollama
    assert "model-runtime" in gpu  # gpu: local vLLM
    assert "model-runtime" not in cloud  # cloud: hosted provider, no local runtime
