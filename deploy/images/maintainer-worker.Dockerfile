# syntax=docker/dockerfile:1
# Maintainer worker: runs scheduled background intelligence (contradictions, refresh, foresight,
# wiki patches) over memory and evidence.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv
RUN pip install --no-cache-dir uv
WORKDIR /app

COPY . /app
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "--no-dev", "metis-maintainer-worker"]
