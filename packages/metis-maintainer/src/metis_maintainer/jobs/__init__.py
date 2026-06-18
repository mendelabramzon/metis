"""Maintainer jobs: the framework primitives and the concrete background jobs.

Each job declares its ``kind``, ``triggers``, and an ``idempotency_key``; the scheduler turns
those into deterministic queue jobs and the worker dispatches them. ``lint_wiki`` and the
wiki claim-support checks are proposal-time validators (functions) invoked by
``compile_wiki_patches``; ``validate_claim_support`` also exposes a standalone memory health job.
"""

from __future__ import annotations

from metis_maintainer.jobs.base import (
    JobOutcome,
    MaintainerDeps,
    MaintainerJob,
    Trigger,
    build_deps,
    workspace_of,
)
from metis_maintainer.jobs.build_foresights import BuildForesightsJob, TimelineForesightBuilder
from metis_maintainer.jobs.compile_wiki_patches import CompileWikiPatchesJob, compile_patch
from metis_maintainer.jobs.detect_contradictions import (
    ClaimContradictionDetector,
    DetectContradictionsJob,
)
from metis_maintainer.jobs.lint_wiki import lint_issues
from metis_maintainer.jobs.refresh_profile import RefreshProfileJob
from metis_maintainer.jobs.refresh_scenes import RefreshScenesJob
from metis_maintainer.jobs.revise_episodes import ReviseEpisodesJob
from metis_maintainer.jobs.validate_claim_support import (
    ValidateClaimSupportJob,
    claim_support_issues,
    is_supported,
)
from metis_maintainer.jobs.validate_deletions import ValidateDeletionsJob

__all__ = [
    "BuildForesightsJob",
    "ClaimContradictionDetector",
    "CompileWikiPatchesJob",
    "DetectContradictionsJob",
    "JobOutcome",
    "MaintainerDeps",
    "MaintainerJob",
    "RefreshProfileJob",
    "RefreshScenesJob",
    "ReviseEpisodesJob",
    "TimelineForesightBuilder",
    "Trigger",
    "ValidateClaimSupportJob",
    "ValidateDeletionsJob",
    "build_deps",
    "claim_support_issues",
    "compile_patch",
    "is_supported",
    "lint_issues",
    "workspace_of",
]
