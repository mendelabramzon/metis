"""The Stage 1 ClaimStore contract, run against real Postgres."""

import pytest

from metis_core.stores import PostgresClaimStore
from metis_protocol.contract_tests import ClaimStoreContract


class TestPostgresClaimStore(ClaimStoreContract):
    @pytest.fixture
    def claim_store(self, sessionmaker):
        return PostgresClaimStore(sessionmaker)
