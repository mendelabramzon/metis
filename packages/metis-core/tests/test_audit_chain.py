"""The per-workspace audit chain verifies and detects tampering."""

from sqlalchemy import select

from metis_core.audit import verify_chain
from metis_core.models import AuditEventRow
from metis_core.stores import PostgresClaimStore, PostgresMinioArtifactStore
from metis_protocol.examples import WS, extraction_batch, raw_artifact


async def test_chain_verifies_after_writes(sessionmaker, object_store):
    artifacts = PostgresMinioArtifactStore(sessionmaker, object_store)
    claims = PostgresClaimStore(sessionmaker)
    await artifacts.put(raw_artifact())
    await claims.write(extraction_batch())

    async with sessionmaker() as session:
        status = await verify_chain(session, str(WS))
    assert status.ok
    assert status.checked >= 2


async def test_tampering_is_detected(sessionmaker, object_store):
    artifacts = PostgresMinioArtifactStore(sessionmaker, object_store)
    await artifacts.put(raw_artifact())

    # Tamper with a recorded audit event's body.
    async with sessionmaker() as session:
        row = (await session.execute(select(AuditEventRow).limit(1))).scalars().one()
        body = dict(row.body)
        body["action"] = "tampered"
        row.body = body
        await session.commit()

    async with sessionmaker() as session:
        status = await verify_chain(session, str(WS))
    assert not status.ok
    assert status.reason == "hash mismatch"
