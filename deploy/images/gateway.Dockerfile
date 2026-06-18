# syntax=docker/dockerfile:1
# The API gateway (and the one-shot `migrate` step reuse this image). Build context is the repo
# root so the whole uv workspace is available.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv
RUN pip install --no-cache-dir uv
WORKDIR /app

COPY . /app
RUN uv sync --frozen --no-dev

EXPOSE 8000
# Serves the API + operator console (uvicorn, wired by metis_gateway.app:run).
CMD ["uv", "run", "--no-dev", "metis-gateway"]
