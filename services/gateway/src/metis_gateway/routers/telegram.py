"""Telegram chat discovery: list the chats the bot has seen on a Business connection.

The Bot API has no "list authorized chats" call, so the ingest worker records chats as their
messages arrive; this exposes them (operator-gated) so a chat can be turned into a source by its
id — the selection step before ``POST /sources`` with a ``telegram`` config.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool

from metis_gateway.deps import BackendDep, CurrentUserDep, OperatorDep
from metis_gateway.errors import ConflictError, NotFoundError
from metis_gateway.schemas import (
    TelegramChatView,
    TelegramConnectCode,
    TelegramConnectPassword,
    TelegramConnectStart,
    TelegramConnectView,
)
from metis_gateway.telegram_connect import (
    ConnectStatus,
    NoActiveConnectError,
    TelegramConnectManager,
)
from metis_ingestion.connectors import ConnectorError

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get("/chats", response_model=list[TelegramChatView])
async def list_discovered_chats(
    backend: BackendDep, _principal: OperatorDep, connection: str | None = None
) -> list[TelegramChatView]:
    """Discovered chats, newest-seen first; filter to one connection with ``?connection=``."""
    chats = await backend.sources.list_discovered_chats(connection)
    return [
        TelegramChatView(
            business_connection_id=chat.business_connection_id,
            chat_id=chat.chat_id,
            chat_type=chat.chat_type,
            title=chat.title,
            last_message_id=chat.last_message_id,
        )
        for chat in chats
    ]


# --- opt-in TDLib personal-account login (per user) --------------------------------------------
#
# Each caller connects *their own* Telegram account, so these are identity-gated (the user-id
# bearer) and keyed by user id, unlike the operator-gated discovery above. The login spans several
# requests (start -> scan QR or enter code -> 2FA), driven by the in-process TelegramConnectManager;
# the blocking tdjson pump is offloaded so it never stalls the event loop.


def connect_manager(request: Request) -> TelegramConnectManager:
    manager: TelegramConnectManager | None = request.app.state.backend.telegram_connect
    if manager is None:
        raise ConflictError("Telegram TDLib connect is not configured")
    return manager


ConnectManagerDep = Annotated[TelegramConnectManager, Depends(connect_manager)]


def _view(status: ConnectStatus) -> TelegramConnectView:
    return TelegramConnectView(state=status.state.value, qr_link=status.qr_link)


_TDLIB_UNAVAILABLE = (
    "Telegram login is unavailable: the TDLib native library (libtdjson) could not be loaded. "
    "Enable the 'telegram' compose profile, or set METIS_GATEWAY_TELEGRAM_TDLIB_LIBRARY to the "
    "path of a libtdjson build."
)


async def _drive(
    call: Callable[..., ConnectStatus], *args: object, **kwargs: object
) -> ConnectStatus:
    """Run a blocking ``TelegramConnectManager`` call off the event loop, mapping its failures to
    typed API errors so a misconfigured host doesn't return a bare 500: a missing/unloadable
    libtdjson (``OSError`` from the ctypes load) and a TDLib runtime/auth failure (a bad api
    id/hash, ``ConnectorError``) both become a clear 409. ``NoActiveConnectError`` is left to
    propagate — the polling/submit endpoints map it to 404."""
    try:
        return await run_in_threadpool(call, *args, **kwargs)
    except OSError as exc:  # ctypes could not load libtdjson (not installed / wrong path)
        raise ConflictError(_TDLIB_UNAVAILABLE) from exc
    except ConnectorError as exc:  # TDLib rejected the login (bad credentials, auth error, ...)
        raise ConflictError(f"Telegram login failed: {exc}") from exc


@router.post("/tdlib/connect", response_model=TelegramConnectView)
async def start_tdlib_connect(
    body: TelegramConnectStart, manager: ConnectManagerDep, user: CurrentUserDep
) -> TelegramConnectView:
    """Begin this user's TDLib login; returns the next step (a QR link, or a code prompt)."""
    status = await _drive(manager.start, str(user.id), use_qr=body.use_qr, phone=body.phone)
    return _view(status)


@router.get("/tdlib/connect", response_model=TelegramConnectView)
async def tdlib_connect_status(
    manager: ConnectManagerDep, user: CurrentUserDep
) -> TelegramConnectView:
    """Poll the login (e.g. while waiting for the QR to be scanned on the phone)."""
    try:
        status = await _drive(manager.status, str(user.id))
    except NoActiveConnectError as exc:
        raise NotFoundError("no TDLib login in progress") from exc
    return _view(status)


@router.post("/tdlib/connect/code", response_model=TelegramConnectView)
async def submit_tdlib_code(
    body: TelegramConnectCode, manager: ConnectManagerDep, user: CurrentUserDep
) -> TelegramConnectView:
    """Submit the login code Telegram delivered to the account."""
    try:
        status = await _drive(manager.submit_code, str(user.id), body.code)
    except NoActiveConnectError as exc:
        raise NotFoundError("no TDLib login in progress") from exc
    return _view(status)


@router.post("/tdlib/connect/password", response_model=TelegramConnectView)
async def submit_tdlib_password(
    body: TelegramConnectPassword, manager: ConnectManagerDep, user: CurrentUserDep
) -> TelegramConnectView:
    """Submit the 2FA (cloud) password when the account has two-step verification enabled."""
    try:
        status = await _drive(manager.submit_password, str(user.id), body.password)
    except NoActiveConnectError as exc:
        raise NotFoundError("no TDLib login in progress") from exc
    return _view(status)
