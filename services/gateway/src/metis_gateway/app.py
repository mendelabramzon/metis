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
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse

from metis_core.observability import setup_telemetry, span
from metis_gateway.backend import build_backend, build_postgres_backend
from metis_gateway.errors import install_error_handlers
from metis_gateway.routers import ALL_ROUTERS
from metis_gateway.settings import GatewaySettings

logger = logging.getLogger("metis_gateway")

_WEB = Path(__file__).parent / "web"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the selected backend at startup (Postgres needs async I/O), dispose it at shutdown."""
    settings: GatewaySettings = app.state.settings
    if settings.backend == "postgres":
        backend = await build_postgres_backend(settings)
    else:
        backend = build_backend(settings)
    app.state.backend = backend
    logger.info("metis-gateway backend ready (%s)", settings.backend)
    try:
        yield
    finally:
        if backend.telegram_connect is not None:
            backend.telegram_connect.close_all()  # release any in-flight TDLib login clients
        for close in backend.model_closers:
            await close()
        if backend.http_client is not None:
            await backend.http_client.aclose()
        if backend.engine is not None:
            await backend.engine.dispose()


def create_app(settings: GatewaySettings | None = None) -> FastAPI:
    """Assemble the app: routers, error handlers, health, the debug UI, and the backend lifespan."""
    settings = settings if settings is not None else GatewaySettings()
    # Telemetry: idempotent and a no-op without OTEL_EXPORTER_OTLP_ENDPOINT, so the served app
    # exports spans/metrics while tests and dry runs pay nothing.
    setup_telemetry(settings.service_name)
    app = FastAPI(title="Metis Gateway", version="0.0.0", lifespan=_lifespan)
    app.state.settings = settings

    @app.middleware("http")
    async def _trace_request(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # A server span per request, carrying the trace_id a queued connector-sync job stashes and
        # the ingest worker later resumes — linking gateway -> worker -> store in one trace.
        with span(
            "http.request", **{"http.method": request.method, "http.route": request.url.path}
        ):
            return await call_next(request)

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
    """Build settings + the app, then serve it with uvicorn (``--dry-run`` wires and stops)."""
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
        return settings

    import uvicorn  # deferred so the app/test import path doesn't require the server

    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower())
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
