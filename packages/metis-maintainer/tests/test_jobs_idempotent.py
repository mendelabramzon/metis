"""Re-running a maintainer job produces no duplicate effects (idempotency)."""

from metis_maintainer.jobs import (
    BuildForesightsJob,
    DetectContradictionsJob,
    RefreshProfileJob,
)
from metis_protocol import BatchId, ExtractionBatch, MemoryScope, new_id
from metis_protocol.examples import CLM2, PDOC, PROV, WS, claim


async def _seed_conflicting_claims(deps) -> None:
    extra = claim().model_copy(update={"id": CLM2, "text": "Ada is the CEO of Acme."})
    await deps.claim_store.write(
        ExtractionBatch(
            id=new_id(BatchId),
            workspace_id=WS,
            parsed_doc_id=PDOC,
            provenance=PROV,
            claims=(claim(), extra),
        )
    )


async def test_detect_contradictions_is_idempotent(deps) -> None:
    await _seed_conflicting_claims(deps)
    scope = MemoryScope(workspace_id=WS)
    payload = {"workspace_id": str(WS), "batch_id": "b1"}

    await DetectContradictionsJob().run(deps, payload)
    after_first = len(await deps.memory_store.query_contradictions(scope))
    await DetectContradictionsJob().run(deps, payload)
    after_second = len(await deps.memory_store.query_contradictions(scope))

    assert after_first >= 1
    assert after_first == after_second  # insert-if-absent: stable contradiction ids


async def test_build_foresights_is_idempotent(deps) -> None:
    await _seed_conflicting_claims(deps)
    scope = MemoryScope(workspace_id=WS)
    payload = {"workspace_id": str(WS)}

    await BuildForesightsJob().run(deps, payload)
    after_first = len(await deps.memory_store.query_foresights(scope))
    await BuildForesightsJob().run(deps, payload)
    after_second = len(await deps.memory_store.query_foresights(scope))

    assert after_first >= 1
    assert after_first == after_second  # day-bucketed id -> upsert, no fork


async def test_refresh_profile_is_idempotent(deps) -> None:
    await _seed_conflicting_claims(deps)
    payload = {"workspace_id": str(WS)}

    first = await RefreshProfileJob().run(deps, payload)
    second = await RefreshProfileJob().run(deps, payload)

    assert first.counts == second.counts  # same profile (upsert) and contradictions
