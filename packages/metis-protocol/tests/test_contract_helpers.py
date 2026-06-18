"""Self-test the abstract contract suites against the reference in-memory fakes.

This proves the suites are importable and correct before ``metis-core`` consumes
them in Stage 2. Each ``Test*`` class inherits the suite's test methods and supplies
the concrete store via a fixture.
"""

import pytest

from metis_protocol.contract_tests import (
    ArtifactStoreContract,
    ClaimStoreContract,
    MemoryStoreContract,
)
from metis_protocol.contract_tests.in_memory import (
    InMemoryArtifactStore,
    InMemoryClaimStore,
    InMemoryMemoryStore,
)
from metis_protocol.interfaces import ArtifactStore, ClaimStore, MemoryStore


class TestInMemoryArtifactStore(ArtifactStoreContract):
    @pytest.fixture
    def artifact_store(self) -> ArtifactStore:
        return InMemoryArtifactStore()


class TestInMemoryClaimStore(ClaimStoreContract):
    @pytest.fixture
    def claim_store(self) -> ClaimStore:
        return InMemoryClaimStore()


class TestInMemoryMemoryStore(MemoryStoreContract):
    @pytest.fixture
    def memory_store(self) -> MemoryStore:
        return InMemoryMemoryStore()
