"""The Stage 1 ArtifactStore contract, run against real Postgres + MinIO."""

import pytest

from metis_core.stores import PostgresMinioArtifactStore
from metis_protocol.contract_tests import ArtifactStoreContract


class TestPostgresArtifactStore(ArtifactStoreContract):
    @pytest.fixture
    def artifact_store(self, sessionmaker, object_store):
        return PostgresMinioArtifactStore(sessionmaker, object_store)
