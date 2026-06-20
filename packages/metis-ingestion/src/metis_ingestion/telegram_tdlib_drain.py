"""Dedicated TDLib backfill drain: per account, open the authorized session and page chat history.

The opt-in TDLib path backfills what the Business bot cannot reach — pre-connection history and
followed channels. Sources are grouped by the account that owns them
(``TelegramSourceConfig.tdlib_user_id``); for each account this opens its already-authorized TDLib
session (the gateway login created the encrypted database; the worker reopens it from the shared db
key), pages each selected chat with :meth:`TelegramTdlibClient.backfill_chat`, and hands the
messages to the same per-chat connector/cursor as the bot path. Backfill is read-only history, so
there are no deletions to tombstone — unlike the live bot drain.

The session-open is the only native part; it is injected as ``account_sessions`` so the suite drives
the whole drain (grouping, backfill, ingest) over a fake tdjson — no ``libtdjson``, no live account.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any

from metis_ingestion.connectors.telegram import TelegramSourceConfig
from metis_ingestion.connectors.telegram_session import TelegramTdlibClient
from metis_protocol import SourceConfig

#: Open one account's authorized backfill client; the context yields ``None`` if it is not
#: authorized (no stored key yet, or revoked) and closes the native client on exit.
AccountSessions = Callable[[str], AbstractContextManager[TelegramTdlibClient | None]]

#: Lookup tables the transport renders with: message-referenced users / chats, keyed by id.
Lookups = Mapping[int, Mapping[str, Any]]

#: Ingest one source's backfilled chat: build its connector over the messages + lookups, resume its
#: cursor, poll once.
SyncTdlibSource = Callable[
    [SourceConfig, Sequence[Mapping[str, Any]], Lookups, Lookups], Awaitable[None]
]


def group_by_account(sources: Sequence[SourceConfig]) -> dict[str, list[SourceConfig]]:
    """Active TDLib chat sources grouped by the account that backfills them.

    TDLib sources are Telegram sources carrying a ``tdlib_user_id`` (bot sources carry a
    ``business_connection_id`` instead); one authorized session per account serves all its chats.
    """
    groups: dict[str, list[SourceConfig]] = {}
    for source in sources:
        if source.connector != "telegram" or not source.active:
            continue
        user_id = TelegramSourceConfig.model_validate(source.config).tdlib_user_id
        if user_id:
            groups.setdefault(user_id, []).append(source)
    return groups


async def drain_tdlib_once(
    *,
    sources: Sequence[SourceConfig],
    account_sessions: AccountSessions,
    sync_source: SyncTdlibSource,
    page_size: int = 50,
    max_pages: int = 20,
) -> int:
    """Backfill every active TDLib source once; return the number of sources synced.

    Opens one authorized session per account and backfills each of its chats through it; an account
    whose session is not authorized is skipped so the others still proceed.
    """
    synced = 0
    for user_id, group in group_by_account(sources).items():
        with account_sessions(user_id) as client:
            if client is None:
                continue  # not authorized for this account; the caller logs, we move on
            for source in group:
                config = TelegramSourceConfig.model_validate(source.config)
                messages, users, chats = client.backfill_chat(
                    config.chat_id, page_size=page_size, max_pages=max_pages
                )
                await sync_source(source, messages, users, chats)
                synced += 1
    return synced
