"""Reusable abstract contract suites that any implementation can run to prove it
satisfies a protocol interface, plus reference in-memory fakes.

Importing this subpackage requires the ``contract-tests`` extra (pytest).
"""

from __future__ import annotations

from metis_protocol.contract_tests.artifact_store import ArtifactStoreContract
from metis_protocol.contract_tests.claim_store import ClaimStoreContract
from metis_protocol.contract_tests.memory_store import MemoryStoreContract

__all__ = [
    "ArtifactStoreContract",
    "ClaimStoreContract",
    "MemoryStoreContract",
]
