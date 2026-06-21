# syntax=docker/dockerfile:1
# The API gateway (and the one-shot `migrate` step reuse this image). Build context is the repo
# root so the whole uv workspace is available.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv
# Put the project venv on PATH so `python` and the console scripts resolve to it (the migrate step
# and the healthchecks run bare `python`, not `uv run`).
ENV PATH="/app/.venv/bin:$PATH"
RUN pip install --no-cache-dir uv
WORKDIR /app

COPY . /app
# --all-packages installs every workspace member (a package=false root installs none otherwise), so
# the image is complete at build time — no lazy `uv run` download at startup, and `migrate` (which
# runs bare `python`) can import metis_deploy/metis_core.
RUN uv sync --frozen --no-dev --all-packages

EXPOSE 8000
# Serves the API + operator console (uvicorn, wired by metis_gateway.app:run).
CMD ["metis-gateway"]
