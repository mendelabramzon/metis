"""The scheduler dedupes by deterministic job id and fans events out to subscribers."""

from metis_core import PostgresJobQueue
from metis_maintainer import MaintenanceScheduler
from metis_protocol import EventName
from metis_protocol.examples import WS


async def test_enqueuing_the_same_unit_twice_is_deduped(sessionmaker) -> None:
    scheduler = MaintenanceScheduler(PostgresJobQueue(sessionmaker))
    payload = {"batch_id": "b1"}

    first = await scheduler.enqueue("detect_contradictions", WS, payload)
    second = await scheduler.enqueue("detect_contradictions", WS, payload)
    assert first == second  # deterministic id from (kind, workspace, idempotency key)

    leased = await PostgresJobQueue(sessionmaker).lease(["detect_contradictions"], 10)
    assert len(leased) == 1  # idempotent enqueue -> a single job, not a duplicate


async def test_on_event_enqueues_every_subscriber(sessionmaker) -> None:
    scheduler = MaintenanceScheduler(PostgresJobQueue(sessionmaker))
    kinds = ("detect_contradictions", "revise_episodes", "refresh_profile")

    job_ids = await scheduler.on_event(EventName.CLAIMS_EXTRACTED, WS, {"batch_id": "b1"})
    assert len(job_ids) == len(kinds)

    leased = await PostgresJobQueue(sessionmaker).lease(list(kinds), 10)
    assert {job.kind for job in leased} == set(kinds)
