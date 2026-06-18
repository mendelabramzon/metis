"""The FastAPI gateway: assembly + the Stage 0 entrypoint (ADR 0009).

``create_app`` wires the backend container onto ``app.state`` and mounts the routers + error
handlers + a minimal debug UI. ``run()`` builds settings and the app and returns the settings
(``--dry-run`` wires-and-stops); actually serving the app with a real ASGI server is wired in
Stage 15 (deployment). The gateway holds no business logic — it is a thin HTTP layer over the
packages (``package-decomposition.md``).
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from metis_gateway.backend import build_backend
from metis_gateway.errors import install_error_handlers
from metis_gateway.routers import ALL_ROUTERS
from metis_gateway.settings import GatewaySettings

logger = logging.getLogger("metis_gateway")

_WEB = Path(__file__).parent / "web"


def create_app(settings: GatewaySettings | None = None) -> FastAPI:
    """Build the FastAPI app: backend wiring, routers, error handlers, health, and the debug UI."""
    settings = settings if settings is not None else GatewaySettings()
    app = FastAPI(title="Metis Gateway", version="0.0.0")
    app.state.settings = settings
    app.state.backend = build_backend(settings)

    install_error_handlers(app)
    for router in ALL_ROUTERS:
        app.include_router(router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index() -> str:
        return (_WEB / "index.html").read_text(encoding="utf-8")

    return app


def run(*, dry_run: bool = False, settings: GatewaySettings | None = None) -> GatewaySettings:
    """Build settings + the app and return the settings; serving itself is Stage 15."""
    settings = settings if settings is not None else GatewaySettings()
    logging.basicConfig(level=settings.log_level)
    app = create_app(settings)
    logger.info(
        "metis-gateway assembled (host=%s port=%s, routes=%d)",
        settings.host,
        settings.port,
        len(app.routes),
    )
    if dry_run:
        logger.info("dry run complete; not serving")
    else:
        logger.info("app assembled; ASGI serving is wired in Stage 15 (deployment)")
    return settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metis-gateway")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build settings and assemble the app, then exit without serving",
    )
    args = parser.parse_args(argv)
    run(dry_run=args.dry_run)
    return 0
