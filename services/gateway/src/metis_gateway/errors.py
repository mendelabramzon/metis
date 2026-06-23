"""One consistent API error shape, so every failure looks the same to a client.

Routers raise a typed :class:`ApiError`; the installed handlers turn it (and FastAPI's own
validation errors) into ``{"error": {"code", "message"}}`` with the right status. Business logic
lives in the packages, so the gateway's error vocabulary is small and HTTP-shaped.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("metis_gateway.errors")


class ApiError(Exception):
    """An error with an HTTP status and a stable machine code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class NotFoundError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(404, "not_found", message)


class UnauthorizedError(ApiError):
    def __init__(self, message: str = "missing or invalid credentials") -> None:
        super().__init__(401, "unauthorized", message)


class ForbiddenError(ApiError):
    def __init__(self, message: str = "insufficient scope") -> None:
        super().__init__(403, "forbidden", message)


class ConflictError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(409, "conflict", message)


class PolicyBlockedError(ApiError):
    """A request refused on policy/sensitivity grounds — not auth, not a server error.

    Distinct from ConflictError so the UI can render a calm "blocked" state with the reason and
    offer no naive retry, rather than treating it as a generic failure.
    """

    def __init__(self, message: str) -> None:
        super().__init__(403, "policy_blocked", message)


class TooManyRequestsError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(429, "too_many_requests", message)


def _error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_error_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content=_error_body("invalid_request", str(exc.errors()))
        )

    @app.exception_handler(Exception)
    async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        # Defense-in-depth: anything that escaped a router without becoming a typed ApiError or a
        # validation error would otherwise leak as Starlette's opaque plain-text 500. The more
        # specific handlers above still take precedence (Starlette only routes genuinely unhandled
        # exceptions here), so this catches the unexpected ones. Log the traceback with the request
        # method/path for observability; return the same machine-readable envelope every other
        # failure uses, with a generic message so internals never reach the client.
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500, content=_error_body("internal_error", "an unexpected error occurred")
        )
