"""Provider-agnostic LLM layer (ADR-0006).

Two layers:

- ``LLMProvider``: one HTTP adapter per vendor. It turns (system prompt, messages,
  JSON Schema) into one JSON object and reports token usage. Nothing else.
- ``StructuredLLM``: what agent nodes use. It sends a Pydantic schema, validates the
  reply, and makes **one corrective re-ask** if the reply doesn't match the schema.
  A second invalid reply raises ``LLMOutputError``, which the node treats as a failure.

Nodes never parse free text: every model output is a validated Pydantic object
(ADR-0005). The graph, nodes and prompts never import a vendor SDK.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypedDict

from pydantic import BaseModel, ValidationError


class LLMMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class Completion:
    data: dict[str, Any]
    model: str
    tokens_in: int = 0
    tokens_out: int = 0


class LLMError(Exception):
    """The provider could not produce an answer (network, auth, rate limit, refusal)."""

    def __init__(self, message: str, *, code: str = "LLM_ERROR", retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        # Filled in by StructuredLLM so failed calls still count against the budget.
        self.records: list[LLMCallRecord] = []
        self.tokens_in = 0
        self.tokens_out = 0


# Errors that no retry or fallback inside this run can fix: the run stops and says why.
FATAL_LLM_CODES = frozenset(
    {
        "LLM_AUTH_FAILED",
        "LLM_QUOTA_EXCEEDED",
        "LLM_MODEL_NOT_FREE",
        "LLM_MODEL_NOT_FOUND",
        "LLM_RATE_LIMITED",
        "LLM_DAILY_LIMIT_REACHED",
    }
)


class LLMOutputError(LLMError):
    """The model answered, but twice with JSON that doesn't match the schema."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="LLM_INVALID_OUTPUT")


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete_json(
        self,
        *,
        purpose: str,
        system: str,
        messages: list[LLMMessage],
        schema_name: str,
        json_schema: dict[str, Any],
        temperature: float,
    ) -> Completion: ...


@dataclass
class LLMCallRecord:
    purpose: str
    prompt_version: str
    provider: str
    model: str
    ok: bool
    latency_ms: int
    tokens_in: int
    tokens_out: int
    reasks: int
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class StructuredResult[T: BaseModel]:
    value: T
    calls: int
    tokens_in: int
    tokens_out: int
    records: list[LLMCallRecord] = field(default_factory=list)


def json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """The model's JSON Schema with ``$ref``s inlined (some providers reject refs)."""
    schema = model.model_json_schema()
    defs: dict[str, Any] = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = defs[ref.removeprefix("#/$defs/")]
                return {**resolve(target), **{k: v for k, v in node.items() if k != "$ref"}}
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    resolved: dict[str, Any] = resolve(schema)
    return resolved


def _validation_summary(error: ValidationError) -> str:
    parts = []
    for issue in error.errors()[:8]:
        where = ".".join(str(p) for p in issue["loc"]) or "(root)"
        parts.append(f"- {where}: {issue['msg']}")
    return "\n".join(parts)


class StructuredLLM:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    @property
    def label(self) -> tuple[str, str]:
        return self.provider.name, self.provider.model

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        prompt_version: str,
        system: str,
        messages: list[LLMMessage],
        schema: type[T],
        temperature: float = 0.0,
    ) -> StructuredResult[T]:
        json_schema = json_schema_for(schema)
        conversation = list(messages)
        records: list[LLMCallRecord] = []
        tokens_in = tokens_out = 0
        for reask in range(2):
            start = time.perf_counter()
            try:
                completion = await self.provider.complete_json(
                    purpose=purpose,
                    system=system,
                    messages=conversation,
                    schema_name=schema.__name__,
                    json_schema=json_schema,
                    temperature=temperature,
                )
            except LLMError as exc:
                records.append(self._record(purpose, prompt_version, start, reask, error=exc))
                exc.records = records
                exc.tokens_in, exc.tokens_out = tokens_in, tokens_out
                raise
            tokens_in += completion.tokens_in
            tokens_out += completion.tokens_out
            try:
                value = schema.model_validate(completion.data)
            except ValidationError as exc:
                records.append(
                    self._record(purpose, prompt_version, start, reask, completion, error=exc)
                )
                conversation = [
                    *conversation,
                    {"role": "assistant", "content": json.dumps(completion.data)[:4000]},
                    {
                        "role": "user",
                        "content": (
                            "Your JSON did not match the required schema:\n"
                            f"{_validation_summary(exc)}\n"
                            "Reply again with corrected JSON only."
                        ),
                    },
                ]
                continue
            records.append(self._record(purpose, prompt_version, start, reask, completion))
            return StructuredResult(value, len(records), tokens_in, tokens_out, records)
        error = LLMOutputError(f"{purpose}: the model returned invalid JSON twice")
        error.records = records
        error.tokens_in, error.tokens_out = tokens_in, tokens_out
        raise error

    def _record(
        self,
        purpose: str,
        prompt_version: str,
        start: float,
        reask: int,
        completion: Completion | None = None,
        *,
        error: Exception | None = None,
    ) -> LLMCallRecord:
        return LLMCallRecord(
            purpose=purpose,
            prompt_version=prompt_version,
            provider=self.provider.name,
            model=completion.model if completion else self.provider.model,
            ok=error is None,
            latency_ms=int((time.perf_counter() - start) * 1000),
            tokens_in=completion.tokens_in if completion else 0,
            tokens_out=completion.tokens_out if completion else 0,
            reasks=reask,
            error=None if error is None else type(error).__name__,
        )
