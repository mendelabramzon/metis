# syntax=docker/dockerfile:1
# Ingestion worker: drains discover/fetch/parse/extract jobs from the core queue.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN pip install --no-cache-dir uv
WORKDIR /app

COPY . /app
# --all-packages: install the whole workspace at build so the image is complete (no startup
# download) and the healthcheck's bare `python -c "import metis_ingest_worker"` resolves.
RUN uv sync --frozen --no-dev --all-packages

CMD ["metis-ingest-worker"]
