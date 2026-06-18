# syntax=docker/dockerfile:1
# Ingestion worker: drains discover/fetch/parse/extract jobs from the core queue.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv
RUN pip install --no-cache-dir uv
WORKDIR /app

COPY . /app
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "--no-dev", "metis-ingest-worker"]
