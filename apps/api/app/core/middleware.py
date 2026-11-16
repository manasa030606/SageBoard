"""HTTP middleware: request ids, access logging, body-size limit and security headers.

Written as pure ASGI middleware (not ``BaseHTTPMiddleware``) so it does not buffer
streaming responses — this matters later for the SSE run-event stream.
"""

from __future__ import annotations

import re
import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_INCOMING_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

log = get_logger("http")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = next(
            (v.decode("latin-1") for k, v in scope["headers"] if k == b"x-request-id"), ""
        )
        # Accept a caller-supplied id only if it is well-formed; otherwise mint one.
        request_id = incoming if _VALID_INCOMING_ID.match(incoming) else f"req_{uuid.uuid4().hex}"
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            log.info(
                "request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_code,
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
            )
            structlog.contextvars.unbind_contextvars("request_id")


JSON_BODY_LIMIT = 1024 * 1024  # the largest legitimate JSON request is a few KB
MULTIPART_OVERHEAD = 1024 * 1024  # form fields and boundaries around an uploaded file


class _BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Refuse oversized request bodies before the application buffers them.

    A declared ``Content-Length`` over the limit is rejected immediately; a body without one
    (chunked) is counted as it is read. Uploads get the configured file limit plus a small
    allowance; everything else gets ``JSON_BODY_LIMIT``.
    """

    def __init__(self, app: ASGIApp, *, upload_path: str, upload_max_bytes: int) -> None:
        self.app = app
        self.upload_path = upload_path
        self.upload_limit = upload_max_bytes + MULTIPART_OVERHEAD

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return
        limit = self.upload_limit if scope["path"] == self.upload_path else JSON_BODY_LIMIT
        declared = next((v for k, v in scope["headers"] if k == b"content-length"), b"")
        if declared.isdigit() and int(declared) > limit:
            await self._refuse(scope, receive, send, limit)
            return

        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLarge:
            if started:
                raise
            await self._refuse(scope, receive, send, limit)

    @staticmethod
    async def _refuse(scope: Scope, receive: Receive, send: Send, limit: int) -> None:
        request_id = scope.get("state", {}).get("request_id")
        log.warning("request_body_too_large", path=scope["path"], limit_bytes=limit)
        body = {
            "error": {
                "code": "REQUEST_TOO_LARGE",
                "message": "The request is too large.",
                "details": {"max_bytes": limit},
                "request_id": request_id,
            }
        }
        await JSONResponse(body, status_code=413)(scope, receive, send)


class SecurityHeadersMiddleware:
    """Headers every API response carries. Responses are private and never cached."""

    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.headers = {
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
            "Cache-Control": "no-store",
        }
        if hsts:  # only meaningful (and only sent) when the API is served over HTTPS
            self.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self.headers.items():
                    if name not in headers:
                        headers[name] = value
            await send(message)

        await self.app(scope, receive, send_wrapper)
