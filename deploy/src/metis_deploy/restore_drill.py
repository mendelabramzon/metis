"""Scheduled restore drill: prove the latest backup is actually restorable, on a schedule.

A backup you have never restored is a hope, not a backup. This restores the most recent bundle into
a *scratch* object store + wiki dir (never the live stores), asserts it round-trips — every blob
comes back and is still content-addressed, the wiki tree is present — and records the outcome as a
metric so an operator is alerted when drills stop passing (the restore-drill freshness alert). It
reuses :func:`metis_core.security.restore` and the live ingest path's content-addressing, so the
drill exercises the real restore path rather than a mock of it.

Run from host cron via the compose one-shot (see ``backup/restore-drill.yml`` and the runbook):

    docker compose -f docker-compose.yml -f backup/restore-drill.yml \\
        --profile restore-drill run --rm restore-drill
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from metis_core.config import CoreSettings
from metis_core.objectstore import S3ObjectStore, content_key
from metis_core.security import BackupManifest, restore
from metis_deploy.observability import flush_telemetry, incr_restore_drill, setup_telemetry
from metis_protocol import ObjectStore

logger = logging.getLogger("metis_restore_drill")

#: Default location of backup bundles inside the backup container (mirrors run-backup.sh).
DEFAULT_BACKUP_ROOT = "/backups"


class RestoreDrillError(RuntimeError):
    """The restore drill could not prove the latest bundle is restorable."""


@dataclass(frozen=True)
class RestoreDrillResult:
    bundle: Path
    blobs: int
    wiki_files: int


def latest_bundle(backup_root: Path | str) -> Path | None:
    """Newest ``backup-*`` bundle under ``backup_root`` (a lexical sort orders the UTC stamps)."""
    root = Path(backup_root)
    if not root.is_dir():
        return None
    bundles = sorted(path for path in root.glob("backup-*") if path.is_dir())
    return bundles[-1] if bundles else None


async def run_restore_drill(
    *,
    object_store: ObjectStore,
    wiki_path: Path | str,
    backup_root: Path | str,
    bundle: Path | str | None = None,
) -> RestoreDrillResult:
    """Restore the latest (or a given) bundle into the scratch stack, verify it round-trips, and
    emit the freshness metric. Records ``outcome=pass`` on success and ``outcome=fail`` (then
    re-raises) on any failure, so the alert in ``observability/alerts.yml`` fires when drills stop.
    """
    try:
        target = Path(bundle) if bundle is not None else latest_bundle(backup_root)
        if target is None:
            raise RestoreDrillError(f"no backup bundle under {backup_root!r} to restore")
        manifest = await restore(object_store=object_store, wiki_path=wiki_path, source=target)
        await _assert_round_trips(object_store, manifest, target)
        incr_restore_drill(outcome="pass")
        logger.info(
            "restore drill PASSED: %s (%d blob(s), %d wiki file(s))",
            target.name,
            len(manifest.blobs),
            manifest.wiki_files,
        )
        return RestoreDrillResult(
            bundle=target, blobs=len(manifest.blobs), wiki_files=manifest.wiki_files
        )
    except Exception:
        incr_restore_drill(outcome="fail")
        logger.exception("restore drill FAILED")
        raise


async def _assert_round_trips(store: ObjectStore, manifest: BackupManifest, bundle: Path) -> None:
    """The restore is not silently empty, and every blob is present and still content-addressed."""
    if not manifest.blobs and manifest.wiki_files == 0:
        raise RestoreDrillError(f"restored bundle {bundle.name} is empty")
    for key in manifest.blobs:
        data = await store.get_bytes(key)
        if data is None:
            raise RestoreDrillError(f"blob {key} missing after restoring {bundle.name}")
        if content_key(data) != key:
            raise RestoreDrillError(
                f"blob {key} failed content-addressing after restoring {bundle.name}"
            )


async def _run(backup_root: str) -> RestoreDrillResult:
    """Wire a scratch object store + wiki dir and run the drill against the latest bundle."""
    core = CoreSettings()
    # A dedicated scratch bucket so a drill never writes into the live artifact store.
    scratch = S3ObjectStore(
        bucket=f"{core.object_store_bucket}-restore-drill",
        endpoint_url=core.object_store_endpoint_url,
        region=core.object_store_region,
        access_key=core.object_store_access_key,
        secret_key=core.object_store_secret_key,
    )
    await scratch.ensure_bucket()
    with tempfile.TemporaryDirectory(prefix="restore-drill-wiki-") as wiki_scratch:
        return await run_restore_drill(
            object_store=scratch, wiki_path=wiki_scratch, backup_root=backup_root
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metis-restore-drill")
    parser.add_argument(
        "--backup-root", default=DEFAULT_BACKUP_ROOT, help="directory holding backup-* bundles"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level="INFO")
    setup_telemetry("restore-drill")  # no-op without OTEL_EXPORTER_OTLP_ENDPOINT
    try:
        asyncio.run(_run(args.backup_root))
        return 0
    except Exception:
        return 1
    finally:
        flush_telemetry()  # a short-lived job must flush before exit or the metric is dropped


if __name__ == "__main__":
    raise SystemExit(main())
