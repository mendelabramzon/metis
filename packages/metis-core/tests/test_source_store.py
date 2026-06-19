"""PostgresSourceStore: durable source configs, resume cursors, and connector-run history.

The load-bearing properties are that configs are workspace-scoped (``list`` only returns a
workspace's own sources — the same tenancy boundary the artifact stores keep), that a cursor
upserts so a re-poll resumes rather than re-ingests, and that a run can open ``RUNNING`` then
close ``SUCCEEDED`` under one id (what the operator source dashboard reads).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from metis_core.stores import PostgresSourceStore
from metis_protocol import (
    ConnectorRun,
    ConnectorRunId,
    ConnectorRunStatus,
    Sensitivity,
    SourceConfig,
    SourceCursor,
    SourceId,
    WorkspaceId,
    new_id,
)

_T = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _config(workspace_id: WorkspaceId, *, name: str = "mailbox") -> SourceConfig:
    return SourceConfig(
        id=new_id(SourceId),
        workspace_id=workspace_id,
        name=name,
        connector="imap",
        sensitivity=Sensitivity.CONFIDENTIAL,
        auth_method="basic",
        created_at=_T,
    )


async def test_register_is_idempotent_by_id(sessionmaker):
    store = PostgresSourceStore(sessionmaker)
    config = _config(new_id(WorkspaceId))

    first = await store.register(config)
    second = await store.register(config.model_copy(update={"name": "renamed"}))

    assert first.id == config.id
    assert second.name == "mailbox"  # the existing row wins; register does not overwrite
    fetched = await store.get(config.id)
    assert fetched is not None
    assert fetched.name == "mailbox"


async def test_list_is_scoped_to_one_workspace(sessionmaker):
    store = PostgresSourceStore(sessionmaker)
    ada_ws, grace_ws = new_id(WorkspaceId), new_id(WorkspaceId)
    ada_src = await store.register(_config(ada_ws, name="ada-mail"))
    await store.register(_config(grace_ws, name="grace-mail"))

    ada_sources = await store.list(ada_ws)
    assert [s.id for s in ada_sources] == [ada_src.id]  # Grace's source is not visible here
    assert {s.name for s in await store.list_all()} >= {"ada-mail", "grace-mail"}


async def test_get_unknown_source_is_none(sessionmaker):
    store = PostgresSourceStore(sessionmaker)
    assert await store.get(new_id(SourceId)) is None
    assert await store.get_cursor(new_id(SourceId)) is None


async def test_cursor_upserts_to_resume_a_sync(sessionmaker):
    store = PostgresSourceStore(sessionmaker)
    source = await store.register(_config(new_id(WorkspaceId)))

    await store.set_cursor(SourceCursor(source_id=source.id, cursor="uid-100", updated_at=_T))
    later = _T + timedelta(minutes=5)
    await store.set_cursor(SourceCursor(source_id=source.id, cursor="uid-220", updated_at=later))

    resumed = await store.get_cursor(source.id)
    assert resumed is not None
    assert resumed.cursor == "uid-220"  # the upsert advanced the resume point in place
    assert resumed.updated_at == later


async def test_connector_run_opens_then_closes_under_one_id(sessionmaker):
    store = PostgresSourceStore(sessionmaker)
    source = await store.register(_config(new_id(WorkspaceId)))
    run_id = new_id(ConnectorRunId)

    await store.record_run(
        ConnectorRun(
            id=run_id,
            source_id=source.id,
            workspace_id=source.workspace_id,
            status=ConnectorRunStatus.RUNNING,
            started_at=_T,
        )
    )
    await store.record_run(
        ConnectorRun(
            id=run_id,
            source_id=source.id,
            workspace_id=source.workspace_id,
            status=ConnectorRunStatus.SUCCEEDED,
            started_at=_T,
            finished_at=_T + timedelta(seconds=30),
            artifacts=3,
            claims=7,
        )
    )

    runs = await store.runs_for(source.id)
    assert len(runs) == 1  # same id upserted, not appended
    assert runs[0].status is ConnectorRunStatus.SUCCEEDED
    assert (runs[0].artifacts, runs[0].claims) == (3, 7)


async def test_runs_for_is_newest_first_and_limited(sessionmaker):
    store = PostgresSourceStore(sessionmaker)
    source = await store.register(_config(new_id(WorkspaceId)))
    for i in range(3):
        await store.record_run(
            ConnectorRun(
                id=new_id(ConnectorRunId),
                source_id=source.id,
                workspace_id=source.workspace_id,
                status=ConnectorRunStatus.SUCCEEDED,
                started_at=_T + timedelta(minutes=i),
            )
        )

    recent = await store.runs_for(source.id, limit=2)
    assert len(recent) == 2
    assert recent[0].started_at > recent[1].started_at  # newest first
