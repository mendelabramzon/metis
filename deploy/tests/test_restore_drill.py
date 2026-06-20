"""The restore drill round-trips the latest backup bundle into a scratch stack and records its
outcome (pass/fail) — the freshness signal the restore-drill alert watches."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from metis_core import observability
from metis_core.objectstore import content_key
from metis_deploy import RestoreDrillError, latest_bundle, run_backup, run_restore_drill
from metis_deploy.observability import Metric


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


@pytest.fixture
def reader() -> Iterator[InMemoryMetricReader]:
    saved_counters = dict(observability._counters)
    saved_histograms = dict(observability._histograms)
    in_memory = InMemoryMetricReader()
    observability.install_instruments(MeterProvider(metric_readers=[in_memory]).get_meter("metis"))
    try:
        yield in_memory
    finally:
        observability._counters.clear()
        observability._counters.update(saved_counters)
        observability._histograms.clear()
        observability._histograms.update(saved_histograms)


def _drill_outcomes(reader: InMemoryMetricReader) -> dict[str, float]:
    data = reader.get_metrics_data()
    outcomes: dict[str, float] = {}
    if data is None:
        return outcomes
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name == Metric.RESTORE_DRILL_RUNS.value:
                    for point in metric.data.data_points:
                        outcomes[point.attributes["outcome"]] = point.value
    return outcomes


async def _make_backup(tmp_path: Path) -> dict[str, bytes]:
    store = InMemoryObjectStore()
    blobs = {content_key(b"memo"): b"memo", content_key(b"roadmap"): b"roadmap"}
    for key, data in blobs.items():
        await store.put_bytes(key, data)
    wiki = tmp_path / "wiki"
    (wiki / "pages").mkdir(parents=True)
    (wiki / "pages" / "acme.md").write_text("# Acme", encoding="utf-8")
    await run_backup(
        object_store=store,
        object_keys=list(blobs),
        wiki_path=wiki,
        backup_root=tmp_path / "backups",
    )
    return blobs


async def test_drill_passes_on_a_restorable_bundle(
    tmp_path: Path, reader: InMemoryMetricReader
) -> None:
    blobs = await _make_backup(tmp_path)
    scratch = InMemoryObjectStore()

    result = await run_restore_drill(
        object_store=scratch,
        wiki_path=tmp_path / "scratch-wiki",
        backup_root=tmp_path / "backups",
    )

    assert result.blobs == len(blobs)
    assert result.wiki_files == 1
    for key, data in blobs.items():  # every blob is back in the scratch store, content-addressed
        assert await scratch.get_bytes(key) == data
    assert (tmp_path / "scratch-wiki" / "pages" / "acme.md").exists()
    assert _drill_outcomes(reader) == {"pass": 1}


async def test_drill_fails_when_there_is_no_bundle(
    tmp_path: Path, reader: InMemoryMetricReader
) -> None:
    with pytest.raises(RestoreDrillError):
        await run_restore_drill(
            object_store=InMemoryObjectStore(),
            wiki_path=tmp_path / "w",
            backup_root=tmp_path / "empty",
        )
    assert _drill_outcomes(reader) == {"fail": 1}


def test_latest_bundle_picks_the_newest(tmp_path: Path) -> None:
    root = tmp_path / "backups"
    root.mkdir()
    (root / "backup-20260101T000000Z").mkdir()
    (root / "backup-20260601T000000Z").mkdir()
    newest = latest_bundle(root)
    assert newest is not None
    assert newest.name == "backup-20260601T000000Z"
    assert latest_bundle(tmp_path / "missing") is None
