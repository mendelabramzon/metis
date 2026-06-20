"""``PostgresSourceStore``: connector source configs, resume cursors, and connector-run history.

The durable substrate that replaces the gateway's in-memory source registry: the ingest worker
reads configs to know what to poll and threads :class:`SourceCursor` across polls so a re-poll
resumes rather than re-ingests; the operator source dashboard reads :class:`ConnectorRun` rows for
sync state and failures. Config writes are idempotent by id; cursors and runs upsert (a cursor
advances; a run opens ``RUNNING`` then closes ``SUCCEEDED``/``FAILED`` under the same id).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.db.session import unit_of_work
from metis_core.mappers import (
    connector_run_to_row,
    source_config_to_row,
    source_cursor_to_row,
    telegram_chat_to_row,
    to_model,
)
from metis_core.models import (
    ConnectorRunRow,
    SourceConfigRow,
    SourceCursorRow,
    TelegramChatRow,
)
from metis_protocol import (
    ConnectorRun,
    SourceConfig,
    SourceCursor,
    SourceId,
    TelegramDiscoveredChat,
    WorkspaceId,
)


class PostgresSourceStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    # --- source configs -----------------------------------------------------------------

    async def register(self, config: SourceConfig) -> SourceConfig:
        async with unit_of_work(self._sessionmaker) as session:
            existing = await session.get(SourceConfigRow, str(config.id))
            if existing is not None:
                return to_model(existing, SourceConfig)
            session.add(source_config_to_row(config))
        return config

    async def get(self, source_id: SourceId) -> SourceConfig | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(SourceConfigRow, str(source_id))
        return to_model(row, SourceConfig) if row is not None else None

    async def set_active(self, source_id: SourceId, active: bool) -> SourceConfig | None:
        """Pause/resume a source; ``active`` lives both as a column and in the ``body``, so set both
        (a new dict so SQLAlchemy notices it). Used to pause a Telegram source on revocation."""
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(SourceConfigRow, str(source_id))
            if row is None:
                return None
            row.active = active
            row.body = {**row.body, "active": active}
            return to_model(row, SourceConfig)

    async def list(self, workspace_id: WorkspaceId) -> Sequence[SourceConfig]:
        """The workspace's sources, oldest first — what the ingest worker polls for a workspace."""
        stmt = (
            select(SourceConfigRow)
            .where(SourceConfigRow.workspace_id == str(workspace_id))
            .order_by(SourceConfigRow.created_at.asc())
        )
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [to_model(row, SourceConfig) for row in rows]

    async def list_all(self) -> Sequence[SourceConfig]:
        """Every configured source, oldest first — the operator source dashboard's view."""
        stmt = select(SourceConfigRow).order_by(SourceConfigRow.created_at.asc())
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [to_model(row, SourceConfig) for row in rows]

    # --- resume cursors (one per source, upserted) --------------------------------------

    async def get_cursor(self, source_id: SourceId) -> SourceCursor | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(SourceCursorRow, str(source_id))
        return to_model(row, SourceCursor) if row is not None else None

    async def set_cursor(self, cursor: SourceCursor) -> SourceCursor:
        async with unit_of_work(self._sessionmaker) as session:
            existing = await session.get(SourceCursorRow, str(cursor.source_id))
            if existing is None:
                session.add(source_cursor_to_row(cursor))
            else:
                existing.schema_version = cursor.schema_version
                existing.updated_at = cursor.updated_at
                existing.body = cursor.model_dump(mode="json")
        return cursor

    # --- Telegram discovered chats (per connection+chat, upserted as messages arrive) -----

    async def upsert_discovered_chat(self, chat: TelegramDiscoveredChat) -> TelegramDiscoveredChat:
        async with unit_of_work(self._sessionmaker) as session:
            existing = await session.get(
                TelegramChatRow, (chat.business_connection_id, chat.chat_id)
            )
            if existing is None:
                session.add(telegram_chat_to_row(chat))
            else:
                existing.schema_version = chat.schema_version
                existing.last_seen_at = chat.last_seen_at
                existing.body = chat.model_dump(mode="json")
        return chat

    async def list_discovered_chats(
        self, business_connection_id: str | None = None
    ) -> Sequence[TelegramDiscoveredChat]:
        """Discovered chats, most-recently-seen first; filtered to one connection when given."""
        stmt = select(TelegramChatRow).order_by(TelegramChatRow.last_seen_at.desc())
        if business_connection_id is not None:
            stmt = stmt.where(TelegramChatRow.business_connection_id == business_connection_id)
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [to_model(row, TelegramDiscoveredChat) for row in rows]

    # --- connector-run history (upserted by id: open then close) ------------------------

    async def record_run(self, run: ConnectorRun) -> ConnectorRun:
        async with unit_of_work(self._sessionmaker) as session:
            existing = await session.get(ConnectorRunRow, str(run.id))
            if existing is None:
                session.add(connector_run_to_row(run))
            else:
                existing.schema_version = run.schema_version
                existing.status = run.status.value
                existing.body = run.model_dump(mode="json")
        return run

    async def runs_for(self, source_id: SourceId, *, limit: int = 50) -> Sequence[ConnectorRun]:
        """A source's recent connector runs, newest first (the dashboard's per-source history)."""
        stmt = (
            select(ConnectorRunRow)
            .where(ConnectorRunRow.source_id == str(source_id))
            .order_by(ConnectorRunRow.started_at.desc())
            .limit(limit)
        )
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [to_model(row, ConnectorRun) for row in rows]

    async def delete(self, source_id: SourceId) -> None:
        """Remove the source registration: its run history, resume cursor, and config. The artifacts
        it produced are erased separately (right-to-erasure), not here."""
        sid = str(source_id)
        async with unit_of_work(self._sessionmaker) as session:
            await session.execute(
                sa_delete(ConnectorRunRow).where(ConnectorRunRow.source_id == sid)
            )
            await session.execute(
                sa_delete(SourceCursorRow).where(SourceCursorRow.source_id == sid)
            )
            await session.execute(sa_delete(SourceConfigRow).where(SourceConfigRow.id == sid))
