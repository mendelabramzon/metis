"""Backup/restore round-trips the object-store blobs and the wiki repo on a fixture workspace."""

from __future__ import annotations

import shutil

from metis_core.objectstore import content_key
from metis_core.security import back_up, restore


async def test_backup_then_restore_round_trips(object_store_mem, tmp_path) -> None:
    # seed object-store blobs and a small wiki tree
    blobs = {content_key(b"alpha"): b"alpha", content_key(b"beta"): b"beta"}
    for key, data in blobs.items():
        await object_store_mem.put_bytes(key, data)
    wiki = tmp_path / "wiki"
    (wiki / "pages").mkdir(parents=True)
    (wiki / "pages" / "acme.md").write_text("# Acme", encoding="utf-8")
    dest = tmp_path / "backup"

    manifest = await back_up(
        object_store=object_store_mem, object_keys=list(blobs), wiki_path=wiki, dest=dest
    )
    assert set(manifest.blobs) == set(blobs)
    assert manifest.wiki_files == 1

    # wipe both stores, then restore
    object_store_mem.objects.clear()
    shutil.rmtree(wiki)

    restored = await restore(object_store=object_store_mem, wiki_path=wiki, source=dest)
    assert set(restored.blobs) == set(blobs)
    for key, data in blobs.items():
        assert await object_store_mem.get_bytes(key) == data
    assert (wiki / "pages" / "acme.md").read_text(encoding="utf-8") == "# Acme"
