"""The TLS proxy overlay fronts the gateway: Caddy terminates HTTPS and forwards to gateway:8000,
and the gateway's own published port is reset so only the proxy is exposed to the host."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1]
PROXY = DEPLOY / "compose" / "proxy.yml"
CADDYFILE = DEPLOY / "compose" / "Caddyfile"


def test_caddyfile_reverse_proxies_to_the_gateway() -> None:
    text = CADDYFILE.read_text(encoding="utf-8")
    assert "reverse_proxy gateway:8000" in text  # forwards every route (incl. /health) to gateway
    assert "{$METIS_DOMAIN:localhost}" in text  # one domain, localhost default


def test_proxy_overlay_terminates_tls_and_unpublishes_the_gateway() -> None:
    text = PROXY.read_text(encoding="utf-8")
    assert "image: caddy" in text
    assert '"443:443"' in text  # HTTPS ingress
    assert "compose/Caddyfile:/etc/caddy/Caddyfile" in text  # mounts the routing config
    assert "ports: !reset []" in text  # the gateway's direct port is reset behind the proxy


def test_compose_config_merges_when_docker_is_available() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker not installed")
    version = subprocess.run([docker, "compose", "version"], capture_output=True, text=True)
    if version.returncode != 0:
        pytest.skip("docker compose plugin not available")
    result = subprocess.run(
        [docker, "compose", "-f", "docker-compose.yml", "-f", "compose/proxy.yml", "config"],
        cwd=DEPLOY,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "proxy" in result.stdout
    assert "caddy" in result.stdout
