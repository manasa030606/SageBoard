"""HTTP adapters for real LLM providers.

Each adapter asks for **one JSON object matching a JSON Schema**:

- Anthropic: a single forced tool (``tool_choice = {"type": "tool"}``) whose
  ``input_schema`` is the schema; the tool input is the answer.
- OpenAI (and Gemini through its OpenAI-compatible endpoint): ``response_format`` of
  type ``json_schema``. ``strict`` is off because Pydantic schemas use optional fields
  and defaults, which strict mode rejects; ``StructuredLLM`` validates the reply anyway.

Transient failures (429, 5xx, timeouts, connection errors) are retried twice with a
short backoff; anything else fails fast. API keys are only ever read from settings and
sent in headers. They never appear in logs, errors or traces.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from app.agent.llm.client import Completion, LLMError, LLMMessage

RETRY_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504, 529})
MAX_TRANSPORT_RETRIES = 2
MAX_RATE_LIMIT_RETRIES = 3
MAX_RATE_LIMIT_WAIT_S = 65.0  # a per-minute limit clears within a minute
HTTP_NOT_FOUND = 404
HTTP_BAD_REQUEST = 400
MAX_OUTPUT_TOKENS = 32_000
WINDOW_S = 60.0
ANTHROPIC_VERSION = "2023-06-01"
HTTP_ERROR = 400
HTTP_TOO_MANY = 429
AUTH_STATUSES = frozenset({401, 403})
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


log = structlog.get_logger("app.agent.llm")


@dataclass
class ErrorInfo:
    """The parts of a provider error body that decide what to do next."""

    message: str = ""
    status: str = ""  # Google: RESOURCE_EXHAUSTED, INVALID_ARGUMENT…
    code: str = ""  # OpenAI: insufficient_quota, rate_limit_exceeded…
    quota_ids: list[str] = field(default_factory=list)
    quota_values: list[str] = field(default_factory=list)
    retry_delay_s: float | None = None


def parse_error_body(response: httpx.Response) -> ErrorInfo:
    """Read OpenAI-style and Google-style error bodies (a dict, or a list of dicts)."""
    try:
        body: Any = response.json()
    except ValueError:
        return ErrorInfo(message=_short(response.text))
    if isinstance(body, list):
        body = body[0] if body else {}
    error = body.get("error", body) if isinstance(body, dict) else {}
    if not isinstance(error, dict):
        return ErrorInfo(message=_short(str(error)))
    info = ErrorInfo(
        message=_short(str(error.get("message", ""))),
        status=str(error.get("status", "")),
        code=str(error.get("code", "") if isinstance(error.get("code"), str) else ""),
    )
    for detail in error.get("details", []) or []:
        if not isinstance(detail, dict):
            continue
        for violation in detail.get("violations", []) or []:
            if isinstance(violation, dict):
                info.quota_ids.append(str(violation.get("quotaId", "")))
                if "quotaValue" in violation:
                    info.quota_values.append(str(violation["quotaValue"]))
        delay = detail.get("retryDelay")
        if isinstance(delay, str) and (m := re.fullmatch(r"(\d+(?:\.\d+)?)s", delay)):
            info.retry_delay_s = float(m.group(1))
    return info


_COSMETIC_SCHEMA_KEYS = frozenset({"title", "default", "examples", "description"})


def simplify_schema(node: Any) -> Any:
    """Drop keywords Google's schema subset may not accept; validation stays in Pydantic."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in _COSMETIC_SCHEMA_KEYS and not isinstance(value, dict):
                continue
            out[key] = (
                simplify_schema(value)
                if key != "properties"
                else {name: simplify_schema(prop) for name, prop in value.items()}
            )
        return out
    if isinstance(node, list):
        return [simplify_schema(v) for v in node]
    return node


class RequestPacer:
    """Client-side requests-per-minute limit, shared by every run in this process.

    Free tiers allow only a few requests per minute; pacing calls here avoids most
    429s instead of reacting to them.
    """

    def __init__(
        self,
        per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.per_minute = per_minute
        self._clock = clock
        self._sleep = sleep
        self._sent: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Wait until another request may be sent; returns the seconds waited."""
        if self.per_minute <= 0:
            return 0.0
        waited = 0.0
        async with self._lock:
            while True:
                now = self._clock()
                while self._sent and now - self._sent[0] >= WINDOW_S:
                    self._sent.popleft()
                if len(self._sent) < self.per_minute:
                    self._sent.append(now)
                    return waited
                delay = WINDOW_S - (now - self._sent[0]) + 0.05
                waited += delay
                await self._sleep(delay)


def _short(text: str, limit: int = 300) -> str:
    return " ".join(text.split())[:limit]


class _HTTPProvider:
    name = "base"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_s: float,
        max_output_tokens: int,
        send_temperature: bool,
        transport: httpx.AsyncBaseTransport | None = None,
        backoff_s: float = 1.0,
        pacer: RequestPacer | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        reasoning_effort: str | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_s
        self._max_tokens = max_output_tokens
        self._send_temperature = send_temperature
        self._transport = transport
        self._backoff = backoff_s
        self._pacer = pacer
        self._sleep = sleep
        self._reasoning_effort = reasoning_effort  # OpenAI-compatible APIs only

    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    async def _complete_once(
        self,
        *,
        purpose: str,
        system: str,
        messages: list[LLMMessage],
        schema_name: str,
        json_schema: dict[str, Any],
        temperature: float,
        max_tokens: int,
    ) -> Completion:
        raise NotImplementedError

    async def complete_json(
        self,
        *,
        purpose: str,
        system: str,
        messages: list[LLMMessage],
        schema_name: str,
        json_schema: dict[str, Any],
        temperature: float,
    ) -> Completion:
        """One structured reply. If the output is cut off (thinking models spend part of
        the token budget reasoning), retry once with double the output budget."""
        tokens = self._max_tokens
        for attempt in range(2):
            try:
                return await self._complete_once(
                    purpose=purpose,
                    system=system,
                    messages=messages,
                    schema_name=schema_name,
                    json_schema=json_schema,
                    temperature=temperature,
                    max_tokens=tokens,
                )
            except LLMError as exc:
                if exc.code != "LLM_TRUNCATED" or attempt == 1 or tokens >= MAX_OUTPUT_TOKENS:
                    raise
                tokens = min(tokens * 2, MAX_OUTPUT_TOKENS)
                log.info("llm.truncated_retry", provider=self.name, max_tokens=tokens)
        raise AssertionError("unreachable")  # pragma: no cover

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        transient_left, rate_limit_left = MAX_TRANSPORT_RETRIES, MAX_RATE_LIMIT_RETRIES
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
            while True:
                if self._pacer is not None:
                    await self._pacer.acquire()
                wait: float | None
                try:
                    response = await http.post(
                        f"{self._base_url}{path}", headers=self._headers(), json=body
                    )
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    error = LLMError(
                        f"{self.name}: network error ({type(exc).__name__})",
                        code="LLM_UNAVAILABLE",
                        retryable=True,
                    )
                    wait = self._backoff * (2 ** (MAX_TRANSPORT_RETRIES - transient_left))
                else:
                    if response.status_code < HTTP_ERROR:
                        data: dict[str, Any] = response.json()
                        return data
                    error, wait = self._http_error(response)
                if not error.retryable or wait is None:
                    raise error
                if error.code == "LLM_RATE_LIMITED":
                    if rate_limit_left == 0 or wait > MAX_RATE_LIMIT_WAIT_S:
                        raise error
                    rate_limit_left -= 1
                else:
                    if transient_left == 0:
                        raise error
                    transient_left -= 1
                log.info("llm.retry", provider=self.name, code=error.code, wait_s=round(wait, 1))
                await self._sleep(wait)

    def _http_error(self, response: httpx.Response) -> tuple[LLMError, float | None]:
        """Classify an error reply; returns the error and how long to wait before a retry."""
        status = response.status_code
        info = parse_error_body(response)
        header = response.headers.get("retry-after", "")
        header_wait = float(header) if header.replace(".", "", 1).isdigit() else None
        text = f"{info.message} {' '.join(info.quota_ids)}"

        if status in AUTH_STATUSES or "API_KEY_INVALID" in text or "API key not valid" in text:
            return LLMError(
                f"{self.name}: the API key was rejected. Check the key in apps/api/.env.",
                code="LLM_AUTH_FAILED",
            ), None
        if status == HTTP_NOT_FOUND:
            return LLMError(
                f"{self.name}: model “{self.model}” was not found for this API key. "
                "Check LLM_MODEL (scripts/check_llm.py lists what your key can use).",
                code="LLM_MODEL_NOT_FOUND",
            ), None
        if status == HTTP_TOO_MANY or info.status == "RESOURCE_EXHAUSTED":
            if "limit: 0" in info.message or "0" in info.quota_values:
                return LLMError(
                    f"{self.name}: model “{self.model}” has no free-tier quota on this key. "
                    "Choose a free-tier model in LLM_MODEL; Sageboard never switches to paid usage.",
                    code="LLM_MODEL_NOT_FREE",
                ), None
            if (
                any("perday" in q.lower() for q in info.quota_ids)
                or info.code == "insufficient_quota"
            ):
                return LLMError(
                    f"{self.name}: the daily quota for “{self.model}” is used up. "
                    "Google's free-tier daily quota resets at midnight Pacific time.",
                    code="LLM_QUOTA_EXCEEDED",
                ), None
            wait = info.retry_delay_s or header_wait or self._backoff * 4
            return LLMError(
                f"{self.name}: too many requests per minute; waited and retried but the limit "
                "persisted. Try again in a minute.",
                code="LLM_RATE_LIMITED",
                retryable=True,
            ), wait
        retryable = status in RETRY_STATUSES
        return LLMError(
            f"{self.name}: HTTP {status}: {_short(info.message or response.text)}",
            code="LLM_BAD_REQUEST" if status == HTTP_BAD_REQUEST else "LLM_HTTP_ERROR",
            retryable=retryable,
        ), (header_wait or self._backoff) if retryable else None


class AnthropicProvider(_HTTPProvider):
    name = "anthropic"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    async def _complete_once(
        self,
        *,
        purpose: str,
        system: str,
        messages: list[LLMMessage],
        schema_name: str,
        json_schema: dict[str, Any],
        temperature: float,
        max_tokens: int,
    ) -> Completion:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "tools": [
                {
                    "name": schema_name,
                    "description": f"Return the {purpose} result in this exact structure.",
                    "input_schema": json_schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": schema_name},
        }
        if self._send_temperature:
            body["temperature"] = temperature
        data = await self._post("/v1/messages", body)
        if data.get("stop_reason") == "max_tokens":
            raise LLMError(
                f"{self.name}: the reply was cut off at the output-token limit "
                "(raise LLM_MAX_OUTPUT_TOKENS, or set LLM_REASONING_EFFORT=low)",
                code="LLM_TRUNCATED",
            )
        for block in data.get("content", []):
            if block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
                usage = data.get("usage", {})
                return Completion(
                    block["input"],
                    data.get("model", self.model),
                    int(usage.get("input_tokens", 0)),
                    int(usage.get("output_tokens", 0)),
                )
        raise LLMError(f"{self.name}: no structured output in reply", code="LLM_NO_OUTPUT")


class OpenAICompatibleProvider(_HTTPProvider):
    name = "openai"

    def __init__(self, *, provider_name: str = "openai", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.name = provider_name
        # "json_schema" until the provider rejects a schema; then "json_object" with the
        # schema in the prompt (replies are validated by StructuredLLM either way).
        self.structured_mode = "json_schema"

    def _headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self._api_key}", "content-type": "application/json"}

    def _body(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        schema_name: str,
        schema: dict[str, Any],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        if self.structured_mode == "json_schema":
            response_format: dict[str, Any] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": False},
            }
        else:
            response_format = {"type": "json_object"}
            system = (
                f"{system}\n\nReturn one JSON object that matches this JSON Schema "
                f"({schema_name}):\n{json.dumps(schema, separators=(',', ':'))}"
            )
        body: dict[str, Any] = {
            "model": self.model,
            "max_completion_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                *({"role": m["role"], "content": m["content"]} for m in messages),
            ],
            "response_format": response_format,
        }
        if self._send_temperature:
            body["temperature"] = temperature
        if self._reasoning_effort:
            body["reasoning_effort"] = self._reasoning_effort
        return body

    async def _complete_once(
        self,
        *,
        purpose: str,
        system: str,
        messages: list[LLMMessage],
        schema_name: str,
        json_schema: dict[str, Any],
        temperature: float,
        max_tokens: int,
    ) -> Completion:
        schema = simplify_schema(json_schema) if self.name == "google" else json_schema
        try:
            data = await self._post(
                "/chat/completions",
                self._body(
                    system=system,
                    messages=messages,
                    schema_name=schema_name,
                    schema=schema,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
            )
        except LLMError as exc:
            if exc.code != "LLM_BAD_REQUEST" or self.structured_mode != "json_schema":
                raise
            log.warning("llm.schema_rejected_fallback", provider=self.name, code=exc.code)
            self.structured_mode = "json_object"
            data = await self._post(
                "/chat/completions",
                self._body(
                    system=system,
                    messages=messages,
                    schema_name=schema_name,
                    schema=schema,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
            )
        try:
            choice = data["choices"][0]
            content = choice["message"].get("content")
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"{self.name}: unexpected reply shape", code="LLM_NO_OUTPUT") from exc
        if choice.get("finish_reason") == "length":
            raise LLMError(
                f"{self.name}: the reply was cut off at the output-token limit "
                "(raise LLM_MAX_OUTPUT_TOKENS, or set LLM_REASONING_EFFORT=low)",
                code="LLM_TRUNCATED",
            )
        if not content:
            refusal = choice["message"].get("refusal")
            raise LLMError(
                f"{self.name}: no content ({_short(str(refusal or 'empty'))})",
                code="LLM_NO_OUTPUT",
            )
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"_unparseable": _short(content, 500)}  # triggers a corrective re-ask
        if not isinstance(parsed, dict):
            parsed = {"_unexpected": parsed}
        usage = data.get("usage") or {}
        return Completion(
            parsed,
            data.get("model", self.model),
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
        )
