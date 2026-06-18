"""The scheduled backup job: snapshot the object store + wiki via the Stage 14 backup.

A thin operational wrapper over ``metis_core.security.back_up`` that names a timestamped dest and
gathers the blob keys from a caller-supplied source (in production, the artifacts' ``storage_ref``
column; the DB tier is the documented ``pg_dump``). Restore is the Stage 14 ``restore`` (see the
runbook).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from metis_core.security import BackupManifest, back_up
from metis_protocol import ObjectStore


def _stamp(now: datetime | None = None) -> str:
    return (now if now is not None else datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")


async def run_backup(
    *,
    object_store: ObjectStore,
    object_keys: Sequence[str],
    wiki_path: Path | str | None,
    backup_root: Path | str,
    now: datetime | None = None,
) -> tuple[Path, BackupManifest]:
    """Write a timestamped backup bundle under ``backup_root`` and return its path + manifest."""
    dest = Path(backup_root) / f"backup-{_stamp(now)}"
    manifest = await back_up(
        object_store=object_store, object_keys=object_keys, wiki_path=wiki_path, dest=dest
    )
    return dest, manifest
