"""Swappable protocol interfaces. Implementations live in the owning packages
(stores/infra in ``metis-core``, connectors/extractors in ``metis-ingestion``,
and so on). All are runtime-checkable ``Protocol`` types.
"""

from __future__ import annotations

from metis_protocol.interfaces.audit import AuditSink
from metis_protocol.interfaces.connectors import Connector, Extractor, Parser
from metis_protocol.interfaces.infra import JobQueue, ObjectStore
from metis_protocol.interfaces.models import (
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelRouter,
)
from metis_protocol.interfaces.processing import (
    Consolidator,
    ContradictionDetector,
    ForesightBuilder,
)
from metis_protocol.interfaces.retrieval import ContextPacker, Retriever
from metis_protocol.interfaces.skills import Skill, SkillRunner
from metis_protocol.interfaces.stores import (
    ArtifactStore,
    ClaimStore,
    DocumentStore,
    MemoryStore,
    WikiStore,
)

__all__ = [
    "ArtifactStore",
    "AuditSink",
    "ClaimStore",
    "Connector",
    "Consolidator",
    "ContextPacker",
    "ContradictionDetector",
    "DocumentStore",
    "Extractor",
    "ForesightBuilder",
    "JobQueue",
    "MemoryStore",
    "ModelMessage",
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "ModelRouter",
    "ObjectStore",
    "Parser",
    "Retriever",
    "Skill",
    "SkillRunner",
    "WikiStore",
]
