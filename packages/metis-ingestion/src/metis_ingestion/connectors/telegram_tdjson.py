"""Native ``libtdjson`` binding: a deployment-only :class:`TdjsonClient` over ctypes.

The TDLib path's session/client (:mod:`telegram_session`) and transport
(:mod:`telegram_tdlib_transport`) run over an injected
:class:`~metis_ingestion.connectors.telegram_session.TdjsonClient` Protocol — the native library is
never imported there, so the whole replay suite runs with no ``.so`` and no live account. This is
the one module that *does* bind ``libtdjson``, wired only in deployment: it loads the shared library
via ctypes and adapts TDLib's JSON client to that Protocol (``send`` a request, ``receive`` the next
update/response).

It uses TDLib's per-handle JSON interface (``td_json_client_create`` / ``_send`` / ``_receive`` /
``_execute`` / ``_destroy``) rather than the newer global-``td_receive`` multi-client one — each
client owns its own handle, so :meth:`receive` returns only *this* client's stream and several
per-user clients can share one process without a dispatcher stealing each other's updates (the
gateway connect endpoint may drive concurrent logins). The marshalling — JSON encode on send, decode
on receive, NULL→None on timeout — is exercised against a fake library in the suite; only
:func:`load_tdjson_library` (the actual ctypes load) is deployment-only.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
from collections.abc import Mapping
from typing import Any, Protocol, cast


class TdjsonLibrary(Protocol):
    """The five ``libtdjson`` entry points the client needs (a real ctypes ``CDLL``, or a fake)."""

    def td_json_client_create(self) -> Any: ...

    def td_json_client_send(self, client: Any, request: bytes) -> None: ...

    def td_json_client_receive(self, client: Any, timeout: float) -> bytes | None: ...

    def td_json_client_execute(self, client: Any, request: bytes) -> bytes | None: ...

    def td_json_client_destroy(self, client: Any) -> None: ...


def load_tdjson_library(path: str | None = None) -> TdjsonLibrary:
    """Load ``libtdjson`` and declare its signatures (deployment-only; needs the native ``.so``).

    ``path`` overrides discovery; otherwise the platform's library search resolves ``tdjson``.
    """
    location = path or ctypes.util.find_library("tdjson") or "tdjson"
    lib = ctypes.CDLL(location)
    lib.td_json_client_create.restype = ctypes.c_void_p
    lib.td_json_client_create.argtypes = []
    lib.td_json_client_send.restype = None
    lib.td_json_client_send.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.td_json_client_receive.restype = ctypes.c_char_p
    lib.td_json_client_receive.argtypes = [ctypes.c_void_p, ctypes.c_double]
    lib.td_json_client_execute.restype = ctypes.c_char_p
    lib.td_json_client_execute.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.td_json_client_destroy.restype = None
    lib.td_json_client_destroy.argtypes = [ctypes.c_void_p]
    return cast(TdjsonLibrary, lib)


def _encode(request: Mapping[str, Any]) -> bytes:
    return json.dumps(request).encode("utf-8")


def _decode(raw: bytes | None) -> dict[str, Any] | None:
    if not raw:  # NULL pointer (a receive timeout) or empty payload
        return None
    decoded: Any = json.loads(raw)
    return decoded if isinstance(decoded, dict) else None


class NativeTdjsonClient:
    """A ``TdjsonClient`` over native ``libtdjson`` — owns one TDLib JSON client handle.

    Requests/responses are TDLib JSON objects, marshalled to/from bytes here; a flood wait or any
    other error arrives as a normal ``error`` response that the session/client layer interprets.
    Construction quiets TDLib's stderr logging unless ``log_verbosity`` is ``None``; :meth:`close`
    destroys the handle (call it when the session ends — e.g. on logout or worker shutdown).
    """

    def __init__(self, lib: TdjsonLibrary, *, log_verbosity: int | None = 1) -> None:
        self._lib = lib
        self._client = lib.td_json_client_create()
        if log_verbosity is not None:
            self.execute({"@type": "setLogVerbosityLevel", "new_verbosity_level": log_verbosity})

    def send(self, request: Mapping[str, Any]) -> None:
        self._lib.td_json_client_send(self._client, _encode(request))

    def receive(self, timeout: float = 1.0) -> dict[str, Any] | None:
        return _decode(self._lib.td_json_client_receive(self._client, float(timeout)))

    def execute(self, request: Mapping[str, Any]) -> dict[str, Any] | None:
        """Run a synchronous TDLib method (e.g. ``setLogVerbosityLevel``) on this client."""
        return _decode(self._lib.td_json_client_execute(self._client, _encode(request)))

    def close(self) -> None:
        self._lib.td_json_client_destroy(self._client)
