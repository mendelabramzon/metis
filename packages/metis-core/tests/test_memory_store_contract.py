"""The Stage 1 MemoryStore contract, run against real Postgres."""

import pytest

from metis_core.stores import PostgresMemoryStore
from metis_protocol.contract_tests import MemoryStoreContract


class TestPostgresMemoryStore(MemoryStoreContract):
    @pytest.fixture
    def memory_store(self, sessionmaker):
        return PostgresMemoryStore(sessionmaker)
