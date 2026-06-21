#!/bin/sh
# One-shot database migration step, run by the `migrate` compose service before any app service
# starts (depends_on: service_completed_successfully). Single init step — workers never race it.
set -eu

echo "metis: migrating database to head..."
# Run the project venv's python (on PATH from the image) — the image is built with --all-packages,
# so metis_deploy + metis_core are installed; no `uv run` (which would re-sync/download) needed.
python - <<'PY'
import os
from metis_deploy.migrations import run_migrations

run_migrations(os.environ["METIS_CORE_DATABASE_URL"])
print("metis: migrations complete")
PY
