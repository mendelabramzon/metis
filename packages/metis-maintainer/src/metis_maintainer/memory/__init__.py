"""Memory generation/consolidation: the Stage 5 builders and the Consolidator.

Generation logic lives here (the maintainer owns the ``Consolidator`` per the package
decomposition); durable storage and the retrieval indexes live in ``metis-core``. The
LLM-backed steps go through the Stage 4 router; every builder also has a deterministic,
evidence-only fallback so unit tests run without a model.
"""

from __future__ import annotations

from metis_maintainer.memory.consolidate import MemoryConsolidator
from metis_maintainer.memory.foresight import ForesightBuilder
from metis_maintainer.memory.memcell import MemCellBuilder
from metis_maintainer.memory.profile import ProfileBuilder, ProfileResult
from metis_maintainer.memory.prompts import (
    EpisodeSummary,
    ForesightDraft,
    SceneSummary,
    memory_registry,
)
from metis_maintainer.memory.scene import SceneBuilder
from metis_maintainer.memory.supersession import (
    create_patch,
    mark_supersedes,
    retract_patch,
    supersede_patch,
)

__all__ = [
    "EpisodeSummary",
    "ForesightBuilder",
    "ForesightDraft",
    "MemCellBuilder",
    "MemoryConsolidator",
    "ProfileBuilder",
    "ProfileResult",
    "SceneBuilder",
    "SceneSummary",
    "create_patch",
    "mark_supersedes",
    "memory_registry",
    "retract_patch",
    "supersede_patch",
]
