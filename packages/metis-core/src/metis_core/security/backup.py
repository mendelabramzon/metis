"""Backup/restore of the non-DB tiers: object-store blobs + the git wiki repo.

A consistent backup spans three stores — Postgres (a logical ``pg_dump`` in the deployment
profile), the object store, and the git wiki. This module owns the two ``pg_dump`` does not: it
snapshots a set of content-addressed blobs and the wiki working tree into a portable bundle, and
restores them. Blobs are content-addressed, so restore is idempotent (re-putting the same bytes is
a no-op). The DB tier is the documented ``pg_dump`` procedure (ADR 0023).
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from metis_protocol import ObjectStore

_MANIFEST = "manifest.json"


@dataclass(frozen=True)
class BackupManifest:
    blobs: tuple[str, ...]
    wiki_files: int


def _blob_path(root: Path, key: str) -> Path:
    return root / "blobs" / key.replace("/", "__")  # content keys are sharded with slashes


async def back_up(
    *,
    object_store: ObjectStore,
    object_keys: Sequence[str],
    wiki_path: Path | str | None,
    dest: Path | str,
) -> BackupManifest:
    """Snapshot the given blobs and the wiki tree into a portable bundle at ``dest``."""
    dest = Path(dest)
    (dest / "blobs").mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    for key in object_keys:
        data = await object_store.get_bytes(key)
        if data is None:
            continue
        path = _blob_path(dest, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        saved.append(key)

    wiki_files = 0
    if wiki_path is not None and Path(wiki_path).exists():
        shutil.copytree(wiki_path, dest / "wiki", dirs_exist_ok=True)
        wiki_files = sum(1 for path in (dest / "wiki").rglob("*") if path.is_file())

    (dest / _MANIFEST).write_text(
        json.dumps({"blobs": saved, "wiki_files": wiki_files}), encoding="utf-8"
    )
    return BackupManifest(blobs=tuple(saved), wiki_files=wiki_files)


async def restore(
    *,
    object_store: ObjectStore,
    wiki_path: Path | str | None,
    source: Path | str,
) -> BackupManifest:
    """Restore blobs into the object store and the wiki tree from a bundle at ``source``."""
    source = Path(source)
    manifest = json.loads((source / _MANIFEST).read_text(encoding="utf-8"))

    restored: list[str] = []
    for key in manifest["blobs"]:
        path = _blob_path(source, key)
        if path.is_file():
            await object_store.put_bytes(key, path.read_bytes())
            restored.append(key)

    wiki_backup = source / "wiki"
    if wiki_path is not None and wiki_backup.exists():
        destination = Path(wiki_path)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(wiki_backup, destination)

    return BackupManifest(blobs=tuple(restored), wiki_files=int(manifest["wiki_files"]))
