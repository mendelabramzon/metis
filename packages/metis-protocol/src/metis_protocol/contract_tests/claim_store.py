"""Abstract contract suite for :class:`~metis_protocol.interfaces.ClaimStore`."""

from __future__ import annotations

import pytest

from metis_protocol.examples import WS, extraction_batch
from metis_protocol.ids import ClaimId, new_id
from metis_protocol.interfaces import ClaimStore
from metis_protocol.query import ClaimFilter


class ClaimStoreContract:
    @pytest.fixture
    def claim_store(self) -> ClaimStore:
        raise NotImplementedError

    async def test_write_then_get(self, claim_store: ClaimStore) -> None:
        batch = extraction_batch()
        result = await claim_store.write(batch)
        claim = batch.claims[0]
        assert claim.id in result.written_claims
        assert await claim_store.get(claim.id) == claim

    async def test_get_missing_returns_none(self, claim_store: ClaimStore) -> None:
        assert await claim_store.get(new_id(ClaimId)) is None

    async def test_write_is_idempotent(self, claim_store: ClaimStore) -> None:
        batch = extraction_batch()
        await claim_store.write(batch)
        second = await claim_store.write(batch)
        assert second.written_claims == ()
        assert second.skipped >= 1

    async def test_query_by_predicate(self, claim_store: ClaimStore) -> None:
        batch = extraction_batch()
        await claim_store.write(batch)
        predicate = batch.claims[0].predicate
        assert predicate is not None
        hits = await claim_store.query(ClaimFilter(workspace_id=WS, predicate=predicate))
        assert batch.claims[0] in hits
        misses = await claim_store.query(
            ClaimFilter(workspace_id=WS, predicate="no_such_predicate")
        )
        assert list(misses) == []
