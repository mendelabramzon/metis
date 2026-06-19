"""One consistent API error shape, so every failure looks the same to a client.

Routers raise a typed :class:`ApiError`; the installed handlers turn it (and FastAPI's own
validation errors) into ``{"error": {"code", "message"}}`` with the right status. Business logic
lives in the packages, so the gateway's error vocabulary is small and HTTP-shaped.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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
