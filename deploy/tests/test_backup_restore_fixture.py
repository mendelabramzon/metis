"""Backup/restore succeeds on a fixture workspace: object-store blobs + wiki (the Stage 14 path)."""

from __future__ import annotations

import shutil

from metis_core.objectstore import content_key
from metis_core.security import restore
from metis_deploy import run_backup


class InMemoryObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_bytes(self, key: str, data: bytes) -> str:
        self.objects[key] = data
        return key

    async def get_bytes(self, key: str) -> bytes | None:
        return self.objects.get(key)

    async def exists(self, key: str) -> bool:
        return key in self.objects

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)


async def test_backup_job_round_trips_a_fixture_workspace(tmp_path) -> None:
    store = InMemoryObjectStore()
    blobs = {content_key(b"memo"): b"memo", content_key(b"roadmap"): b"roadmap"}
    for key, data in blobs.items():
        await store.put_bytes(key, data)
    wiki = tmp_path / "wiki"
    (wiki / "pages").mkdir(parents=True)
    (wiki / "pages" / "acme.md").write_text("# Acme", encoding="utf-8")

    dest, manifest = await run_backup(
        object_store=store,
        object_keys=list(blobs),
        wiki_path=wiki,
        backup_root=tmp_path / "backups",
    )
    assert dest.name.startswith("backup-")  # timestamped bundle
    assert set(manifest.blobs) == set(blobs)
    assert manifest.wiki_files == 1

    # wipe both stores, then restore from the bundle
    store.objects.clear()
    shutil.rmtree(wiki)

    restored = await restore(object_store=store, wiki_path=wiki, source=dest)
    assert set(restored.blobs) == set(blobs)
    for key, data in blobs.items():
        assert await store.get_bytes(key) == data
    assert (wiki / "pages" / "acme.md").read_text(encoding="utf-8") == "# Acme"
