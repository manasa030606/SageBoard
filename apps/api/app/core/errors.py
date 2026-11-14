"""Domain exceptions and the handlers that map them to the error envelope.

Route handlers and services raise ``AppError`` subclasses; they never build error
responses themselves. Unexpected exceptions become a generic 500 with no internals
in the body (the details go to the log with the request id).
"""

from __future__ import annotations

import socket
from http import HTTPStatus
from typing import Any

import asyncpg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.schemas.errors import ErrorBody, ErrorResponse

log = get_logger(__name__)

DATABASE_UNAVAILABLE_ERRORS: tuple[type[Exception], ...] = (
    OperationalError,
    InterfaceError,
    PoolTimeoutError,
    asyncpg.CannotConnectNowError,
    asyncpg.ConnectionDoesNotExistError,
    asyncpg.InterfaceError,
    asyncpg.InvalidPasswordError,
    asyncpg.InvalidAuthorizationSpecificationError,
    ConnectionError,  # refused / reset while the pool connects lazily
    socket.gaierror,  # database host name doesn't resolve
)


class AppError(Exception):
    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred."

    headers: dict[str, str] | None = None

    def __init__(
        self, message: str | None = None, *, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "NOT_FOUND"
    message = "The requested resource was not found."


class ServiceUnavailableError(AppError):
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "SERVICE_UNAVAILABLE"
    message = "A required service is unavailable."


_STATUS_TO_CODE: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "AUTH_REQUIRED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    429: "RATE_LIMITED",
}


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None


def _envelope(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code, message=message, details=details or {}, request_id=_request_id(request)
        )
    )
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"), headers=headers)


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101 - narrowing for the type checker
    return _envelope(
        request, exc.status_code, exc.code, exc.message, exc.details, headers=exc.headers
    )


async def _http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    code = _STATUS_TO_CODE.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    return _envelope(request, exc.status_code, code, message)


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    fields = [
        {"loc": list(err.get("loc", [])), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return _envelope(
        request, 422, "VALIDATION_ERROR", "The request is invalid.", {"fields": fields}
    )


async def _database_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Database unreachable or failing: 503 with no driver message, host or SQL."""
    log.error(
        "database_error",
        request_id=_request_id(request),
        path=request.url.path,
        error_type=type(getattr(exc, "orig", exc)).__name__,
    )
    return _envelope(
        request,
        503,
        "DATABASE_UNAVAILABLE",
        "The database is unavailable right now. Please try again shortly.",
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_error", request_id=_request_id(request), path=request.url.path)
    return _envelope(request, 500, "INTERNAL_ERROR", "An unexpected error occurred.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    # Connection-level failures only (server down, network, auth to the DB failed,
    # pool timeout). Integrity errors are bugs or races and stay 500s.
    for exc_type in DATABASE_UNAVAILABLE_ERRORS:
        app.add_exception_handler(exc_type, _database_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)


class ValidationFailedError(AppError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "VALIDATION_ERROR"
    message = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        if code:
            self.code = code


class FileTooLargeError(AppError):
    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    code = "FILE_TOO_LARGE"
    message = "The file is too large."


class UnsupportedFileError(AppError):
    status_code = HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    code = "UNSUPPORTED_FILE"
    message = "This file type is not supported."


class ConflictError(AppError):
    status_code = HTTPStatus.CONFLICT
    code = "CONFLICT"
    message = "The request conflicts with the current state."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        if code:
            self.code = code


class AuthRequiredError(AppError):
    status_code = HTTPStatus.UNAUTHORIZED
    code = "AUTH_REQUIRED"
    message = "Please sign in to continue."


class TokenExpiredError(AuthRequiredError):
    code = "TOKEN_EXPIRED"
    message = "Your session has expired. Please sign in again."


class InvalidCredentialsError(AuthRequiredError):
    code = "INVALID_CREDENTIALS"
    message = "That email and password don’t match an account."


class CsrfError(AppError):
    status_code = HTTPStatus.FORBIDDEN
    code = "CSRF_FAILED"
    message = "This request is missing its security token. Reload the page and try again."


class RateLimitedError(AppError):
    status_code = HTTPStatus.TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
    message = "Too many attempts. Please wait and try again."

    def __init__(self, retry_after: int, message: str | None = None) -> None:
        super().__init__(message, details={"retry_after_seconds": retry_after})
        self.headers = {"Retry-After": str(retry_after)}
