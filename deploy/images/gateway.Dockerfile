# syntax=docker/dockerfile:1
# The API gateway (and the one-shot `migrate` step reuse this image). Build context is the repo
# root so the whole uv workspace is available.

# Stage 1: build the React SPA (apps/web -> dist) the gateway serves at /. Kept separate so a
# frontend change doesn't rebuild the Python venv, and the runtime image carries no Node toolchain.
FROM node:20-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

# Stage 2: the gateway runtime.
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

# The built SPA the gateway serves at / (metis_gateway.app reads METIS_GATEWAY_WEB_DIST). Copied
# after the venv so a frontend-only change reuses the uv layer.
COPY --from=web /web/dist /app/web-dist
ENV METIS_GATEWAY_WEB_DIST=/app/web-dist

EXPOSE 8000
# Serves the API + the React SPA (uvicorn, wired by metis_gateway.app:run).
CMD ["metis-gateway"]
