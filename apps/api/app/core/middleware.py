"""HTTP middleware: request ids and access logging.

Written as pure ASGI middleware (not ``BaseHTTPMiddleware``) so it does not buffer
streaming responses — this matters later for the SSE run-event stream.
"""

from __future__ import annotations

import re
import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
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
