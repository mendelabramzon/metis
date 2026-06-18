#!/bin/sh
# Back up the canonical truth tier (Postgres) and the wiki tree to a timestamped bundle.
# Object-store blobs are content-addressed and immutable; snapshot the `miniodata` volume
# alongside this, or use the programmatic metis_deploy.run_backup (see runbook).
set -eu

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="/backups/metis-${STAMP}"
mkdir -p "${OUT}"
echo "metis backup -> ${OUT}"

# Postgres: a custom-format logical dump (restore with pg_restore).
pg_dump "postgresql://metis:${POSTGRES_PASSWORD:-metis}@postgres:5432/metis" \
  --no-owner --format=custom --file "${OUT}/db.dump"

# Wiki: the git-backed projection working tree.
if [ -d /app/wiki ]; then
  tar -C /app/wiki -czf "${OUT}/wiki.tar.gz" .
fi

echo "metis backup complete: ${OUT}"
echo "note: snapshot the minio (object-store) volume to capture artifact blobs."
