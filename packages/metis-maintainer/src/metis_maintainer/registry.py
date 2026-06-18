"""The maintainer job registry and the trigger model.

``build_registry`` maps each job ``kind`` to its instance. ``EVENT_SUBSCRIPTIONS`` declares
which jobs react to which domain events (event-driven), and ``PERIODIC_KINDS`` lists jobs run
on a cadence — chosen per job rather than via a global tick that re-scans everything.
``validate_deletions`` is enqueued explicitly when a deletion is requested, so it is registered
but bound to no standard event.
"""

from __future__ import annotations

from metis_maintainer.jobs import (
    BuildForesightsJob,
    CompileWikiPatchesJob,
    DetectContradictionsJob,
    MaintainerJob,
    RefreshProfileJob,
    RefreshScenesJob,
    ReviseEpisodesJob,
    ValidateClaimSupportJob,
    ValidateDeletionsJob,
)
from metis_protocol import EventName


def build_registry() -> dict[str, MaintainerJob]:
    jobs: list[MaintainerJob] = [
        DetectContradictionsJob(),
        ReviseEpisodesJob(),
        RefreshScenesJob(),
        RefreshProfileJob(),
        BuildForesightsJob(),
        CompileWikiPatchesJob(),
        ValidateClaimSupportJob(),
        ValidateDeletionsJob(),
    ]
    return {job.kind: job for job in jobs}


#: Domain event -> the job kinds it triggers (event-driven). Avoids a global re-scan tick.
EVENT_SUBSCRIPTIONS: dict[EventName, tuple[str, ...]] = {
    EventName.CLAIMS_EXTRACTED: ("detect_contradictions", "revise_episodes", "refresh_profile"),
    EventName.MEMCELL_CREATED: ("refresh_scenes",),
}

#: Jobs run on a cadence rather than in response to a specific event.
PERIODIC_KINDS: tuple[str, ...] = (
    "build_foresights",
    "compile_wiki_patches",
    "validate_claim_support",
)
