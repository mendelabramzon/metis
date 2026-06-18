"""Abstract contract suite for :class:`~metis_protocol.interfaces.ArtifactStore`.

Subclass it in a test module and provide an ``artifact_store`` fixture::

    class TestMyArtifactStore(ArtifactStoreContract):
        @pytest.fixture
        def artifact_store(self) -> ArtifactStore:
            return MyArtifactStore(...)
"""

from __future__ import annotations

import pytest

from metis_protocol.examples import raw_artifact
from metis_protocol.ids import ArtifactId, new_id
from metis_protocol.interfaces import ArtifactStore
from metis_protocol.refs import ArtifactRef


class ArtifactStoreContract:
    @pytest.fixture
    def artifact_store(self) -> ArtifactStore:
        raise NotImplementedError

    async def test_put_then_get_roundtrips(self, artifact_store: ArtifactStore) -> None:
        raw = raw_artifact()
        ref = await artifact_store.put(raw)
        assert await artifact_store.get(ref) == raw

    async def test_get_missing_returns_none(self, artifact_store: ArtifactStore) -> None:
        missing = ArtifactRef(artifact_id=new_id(ArtifactId))
        assert await artifact_store.get(missing) is None

    async def test_put_is_idempotent_by_content_hash(self, artifact_store: ArtifactStore) -> None:
        raw = raw_artifact()
        assert await artifact_store.put(raw) == await artifact_store.put(raw)
