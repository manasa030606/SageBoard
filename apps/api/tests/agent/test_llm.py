"""LLM layer: structured output validation + re-ask, provider adapters (over a mock HTTP
transport — no network, no keys), retries, and the factory."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.agent.llm.client import LLMError, LLMOutputError, StructuredLLM, json_schema_for
from app.agent.llm.factory import build_llm, build_provider
from app.agent.llm.providers import AnthropicProvider, OpenAICompatibleProvider, RequestPacer
from app.agent.state import QueryUnderstanding
from tests.agent.fakes import ScriptedProvider
from tests.conftest import make_settings


class Answer(BaseModel):
    value: int
    label: str


async def test_structured_valid_first_time() -> None:
    llm = StructuredLLM(ScriptedProvider({"p": [{"value": 1, "label": "a"}]}))
    result = await llm.structured(
        purpose="p",
        prompt_version="p.v1",
        system="s",
        messages=[{"role": "user", "content": "q"}],
        schema=Answer,
    )
    assert result.value == Answer(value=1, label="a") and result.calls == 1
    assert result.records[0].ok and result.records[0].prompt_version == "p.v1"


async def test_structured_reasks_once_with_the_validation_errors() -> None:
    provider = ScriptedProvider({"p": [{"value": "not a number"}, {"value": 2, "label": "b"}]})
    result = await StructuredLLM(provider).structured(
        purpose="p",
        prompt_version="v",
        system="s",
        messages=[{"role": "user", "content": "q"}],
        schema=Answer,
    )
    assert result.value.value == 2 and result.calls == 2
    reask = provider.calls[1].messages[-1]["content"]
    assert "did not match the required schema" in reask and "value" in reask and "label" in reask
    assert [r.ok for r in result.records] == [False, True]


async def test_structured_gives_up_after_two_invalid_replies() -> None:
    provider = ScriptedProvider({"p": [{"x": 1}, {"y": 2}]})
    with pytest.raises(LLMOutputError) as info:
        await StructuredLLM(provider).structured(
            purpose="p",
            prompt_version="v",
            system="s",
            messages=[{"role": "user", "content": "q"}],
            schema=Answer,
        )
    assert len(info.value.records) == 2 and info.value.tokens_in == 200


def test_json_schema_inlines_refs() -> None:
    schema = json_schema_for(QueryUnderstanding)
    assert "$defs" not in json.dumps(schema) and "$ref" not in json.dumps(schema)


# ------------------------------------------------------------------ adapters


def _transport(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


COMMON: dict[str, Any] = {
    "api_key": "sk-test-not-real",
    "model": "m-1",
    "timeout_s": 5,
    "max_output_tokens": 512,
    "send_temperature": True,
    "backoff_s": 0,
}


async def test_anthropic_forced_tool_call() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "m-1",
                "stop_reason": "tool_use",
                "content": [
                    {"type": "text", "text": "ok"},
                    {"type": "tool_use", "name": "Answer", "input": {"value": 3, "label": "c"}},
                ],
                "usage": {"input_tokens": 11, "output_tokens": 5},
            },
        )

    provider = AnthropicProvider(
        base_url="https://api.anthropic.test", transport=_transport(handler), **COMMON
    )
    result = await StructuredLLM(provider).structured(
        purpose="p",
        prompt_version="v",
        system="sys",
        messages=[{"role": "user", "content": "q"}],
        schema=Answer,
    )
    assert result.value.value == 3 and result.tokens_in == 11 and result.tokens_out == 5
    assert seen["url"] == "https://api.anthropic.test/v1/messages"
    assert seen["headers"]["x-api-key"] == "sk-test-not-real"
    assert seen["body"]["tool_choice"] == {"type": "tool", "name": "Answer"}
    assert seen["body"]["tools"][0]["input_schema"]["required"] == ["value", "label"]
    assert seen["body"]["system"] == "sys" and seen["body"]["temperature"] == 0.0


async def test_openai_json_schema_response_format() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(
            200,
            json={
                "model": "m-1",
                "usage": {"prompt_tokens": 9, "completion_tokens": 4},
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"value": 4, "label": "d"}'}}
                ],
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://api.openai.test/v1", transport=_transport(handler), **COMMON
    )
    result = await StructuredLLM(provider).structured(
        purpose="p",
        prompt_version="v",
        system="sys",
        messages=[{"role": "user", "content": "q"}],
        schema=Answer,
    )
    assert result.value.label == "d" and result.tokens_in == 9
    assert seen["auth"] == "Bearer sk-test-not-real"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert seen["body"]["response_format"]["type"] == "json_schema"


async def test_openai_unparseable_content_triggers_reask() -> None:
    replies = iter(
        [
            {"choices": [{"message": {"content": "not json"}}]},
            {"choices": [{"message": {"content": '{"value": 5, "label": "e"}'}}]},
        ]
    )
    provider = OpenAICompatibleProvider(
        base_url="https://x.test",
        transport=_transport(lambda r: httpx.Response(200, json=next(replies))),
        **COMMON,
    )
    result = await StructuredLLM(provider).structured(
        purpose="p",
        prompt_version="v",
        system="s",
        messages=[{"role": "user", "content": "q"}],
        schema=Answer,
    )
    assert result.value.value == 5 and result.calls == 2


async def test_transient_errors_are_retried_then_succeed() -> None:
    statuses = iter([503, 429, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "busy"}})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"value": 6, "label": "f"}'}}]}
        )

    provider = OpenAICompatibleProvider(
        base_url="https://x.test", transport=_transport(handler), **COMMON
    )
    result = await StructuredLLM(provider).structured(
        purpose="p",
        prompt_version="v",
        system="s",
        messages=[{"role": "user", "content": "q"}],
        schema=Answer,
    )
    assert result.value.value == 6


@pytest.mark.parametrize(("status", "code"), [(401, "LLM_AUTH_FAILED"), (400, "LLM_BAD_REQUEST")])
async def test_non_retryable_errors_fail_fast_without_leaking_the_key(
    status: int, code: str
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": "bad request"}})

    provider = AnthropicProvider(base_url="https://x.test", transport=_transport(handler), **COMMON)
    with pytest.raises(LLMError) as info:
        await provider.complete_json(
            purpose="p", system="s", messages=[], schema_name="A", json_schema={}, temperature=0
        )
    assert info.value.code == code and len(calls) == 1
    assert "sk-test-not-real" not in str(info.value)


async def test_network_errors_exhaust_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    provider = AnthropicProvider(base_url="https://x.test", transport=_transport(handler), **COMMON)
    with pytest.raises(LLMError) as info:
        await provider.complete_json(
            purpose="p", system="s", messages=[], schema_name="A", json_schema={}, temperature=0
        )
    assert info.value.code == "LLM_UNAVAILABLE"


async def test_truncated_output_is_retried_once_with_double_budget_then_reported() -> None:
    budgets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        budgets.append(json.loads(request.content)["max_tokens"])
        return httpx.Response(200, json={"stop_reason": "max_tokens", "content": []})

    provider = AnthropicProvider(base_url="https://x.test", transport=_transport(handler), **COMMON)
    with pytest.raises(LLMError) as info:
        await provider.complete_json(
            purpose="p", system="s", messages=[], schema_name="A", json_schema={}, temperature=0
        )
    assert info.value.code == "LLM_TRUNCATED" and "LLM_MAX_OUTPUT_TOKENS" in str(info.value)
    assert budgets == [512, 1024]


async def test_truncated_thinking_reply_succeeds_with_more_room() -> None:
    budgets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        budget = json.loads(request.content)["max_completion_tokens"]
        budgets.append(budget)
        if budget < 1024:
            return httpx.Response(
                200, json={"choices": [{"finish_reason": "length", "message": {"content": ""}}]}
            )
        return httpx.Response(200, json=OK_REPLY)

    provider = google_provider(handler, [])
    await call(provider)
    assert budgets == [512, 1024]


async def test_reasoning_effort_is_sent_only_when_configured() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=OK_REPLY)

    for effort in (None, "low"):
        provider = OpenAICompatibleProvider(
            provider_name="google",
            base_url="https://g.test",
            transport=_transport(handler),
            reasoning_effort=effort,
            **COMMON,
        )
        await call(provider)
    assert "reasoning_effort" not in seen[0] and seen[1]["reasoning_effort"] == "low"


async def test_temperature_can_be_omitted() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"value": 1, "label": "x"}'}}]}
        )

    provider = OpenAICompatibleProvider(
        base_url="https://x.test",
        transport=_transport(handler),
        **{**COMMON, "send_temperature": False},
    )
    await provider.complete_json(
        purpose="p", system="s", messages=[], schema_name="A", json_schema={}, temperature=0
    )
    assert "temperature" not in seen


# ------------------------------------------------------------------- factory


def test_mock_provider_builds_no_model() -> None:
    assert build_llm(make_settings(llm_provider="mock")) is None


@pytest.mark.parametrize(
    ("provider", "key_field", "cls", "base"),
    [
        ("anthropic", "anthropic_api_key", AnthropicProvider, "https://api.anthropic.com"),
        ("openai", "openai_api_key", OpenAICompatibleProvider, "https://api.openai.com/v1"),
        (
            "google",
            "google_api_key",
            OpenAICompatibleProvider,
            "https://generativelanguage.googleapis.com/v1beta/openai",
        ),
    ],
)
def test_factory_builds_each_provider(provider: str, key_field: str, cls: type, base: str) -> None:
    settings = make_settings(llm_provider=provider, llm_model="some-model", **{key_field: "k-test"})
    built = build_provider(settings)
    assert (
        built is not None
        and isinstance(built, cls)
        and built.model == "some-model"
        and built.name == provider
    )
    assert built._base_url == base  # type: ignore[attr-defined]


# ------------------------------------------------ Google free tier: 429s and quota


def google_429(
    quota_id: str, *, value: str = "20", delay: str | None = None, message: str = "Quota exceeded"
) -> httpx.Response:
    details: list[dict[str, Any]] = [
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [
                {
                    "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                    "quotaId": quota_id,
                    "quotaValue": value,
                }
            ],
        }
    ]
    if delay:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay})
    body = [
        {
            "error": {
                "code": 429,
                "message": message,
                "status": "RESOURCE_EXHAUSTED",
                "details": details,
            }
        }
    ]
    return httpx.Response(429, json=body)


OK_REPLY = {"choices": [{"message": {"content": '{"value": 1, "label": "x"}'}}]}


def google_provider(handler: Any, sleeps: list[float]) -> OpenAICompatibleProvider:
    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    return OpenAICompatibleProvider(
        provider_name="google",
        base_url="https://g.test",
        transport=_transport(handler),
        sleep=fake_sleep,
        **COMMON,
    )


async def call(provider: OpenAICompatibleProvider) -> None:
    await provider.complete_json(
        purpose="p", system="s", messages=[], schema_name="A", json_schema={}, temperature=0
    )


async def test_per_minute_limit_waits_for_googles_retry_delay_then_succeeds() -> None:
    replies = iter(
        [
            google_429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", delay="7s"),
            httpx.Response(200, json=OK_REPLY),
        ]
    )
    sleeps: list[float] = []
    await call(google_provider(lambda r: next(replies), sleeps))
    assert sleeps == [7.0]


async def test_daily_quota_exhaustion_fails_fast_with_a_clear_message() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return google_429("GenerateRequestsPerDayPerProjectPerModel-FreeTier", delay="40s")

    sleeps: list[float] = []
    with pytest.raises(LLMError) as info:
        await call(google_provider(handler, sleeps))
    assert info.value.code == "LLM_QUOTA_EXCEEDED" and not info.value.retryable
    assert "midnight Pacific" in str(info.value)
    assert calls == [1] and sleeps == []


async def test_model_without_free_tier_quota_is_reported_and_never_retried() -> None:
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return google_429(
            "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
            value="0",
            message="Quota exceeded for metric ... limit: 0, model: gemini-pro-x",
        )

    with pytest.raises(LLMError) as info:
        await call(google_provider(handler, sleeps))
    assert info.value.code == "LLM_MODEL_NOT_FREE" and "never switches to paid" in str(info.value)
    assert sleeps == []


async def test_persistent_rate_limit_gives_up_after_bounded_retries() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return google_429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", delay="2s")

    sleeps: list[float] = []
    with pytest.raises(LLMError) as info:
        await call(google_provider(handler, sleeps))
    assert info.value.code == "LLM_RATE_LIMITED"
    assert len(calls) == 4 and sleeps == [2.0, 2.0, 2.0]


async def test_rate_limit_with_a_long_retry_delay_is_not_waited_out() -> None:
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return google_429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", delay="300s")

    with pytest.raises(LLMError, match="per minute"):
        await call(google_provider(handler, sleeps))
    assert sleeps == []


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (
            httpx.Response(
                400,
                json=[
                    {
                        "error": {
                            "code": 400,
                            "message": "API key not valid. Please pass a valid API key.",
                            "status": "INVALID_ARGUMENT",
                        }
                    }
                ],
            ),
            "LLM_AUTH_FAILED",
        ),
        (
            httpx.Response(
                404,
                json={
                    "error": {
                        "code": 404,
                        "message": "models/gemini-9 is not found",
                        "status": "NOT_FOUND",
                    }
                },
            ),
            "LLM_MODEL_NOT_FOUND",
        ),
        (
            httpx.Response(
                429,
                json={
                    "error": {
                        "message": "You exceeded your current quota",
                        "code": "insufficient_quota",
                    }
                },
            ),
            "LLM_QUOTA_EXCEEDED",
        ),
    ],
)
async def test_google_and_openai_error_shapes_are_classified(
    response: httpx.Response, code: str
) -> None:
    sleeps: list[float] = []
    with pytest.raises(LLMError) as info:
        await call(google_provider(lambda r: response, sleeps))
    assert info.value.code == code and "sk-test-not-real" not in str(info.value)


async def test_pacer_spaces_requests_to_the_per_minute_limit() -> None:
    now = [0.0]
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    pacer = RequestPacer(3, clock=lambda: now[0], sleep=fake_sleep)
    waits = [await pacer.acquire() for _ in range(4)]
    assert waits[:3] == [0.0, 0.0, 0.0] and 59.9 < waits[3] < 60.2
    assert RequestPacer(0).per_minute == 0 and await RequestPacer(0).acquire() == 0.0


async def test_provider_waits_for_the_pacer_before_each_request() -> None:
    order: list[str] = []

    class Pacer(RequestPacer):
        async def acquire(self) -> float:
            order.append("pace")
            return 0.0

    def handler(request: httpx.Request) -> httpx.Response:
        order.append("send")
        return httpx.Response(200, json=OK_REPLY)

    provider = OpenAICompatibleProvider(
        provider_name="google",
        base_url="https://g.test",
        transport=_transport(handler),
        pacer=Pacer(5),
        **COMMON,
    )
    await call(provider)
    assert order == ["pace", "send"]


async def test_google_schema_rejection_falls_back_to_json_mode_once() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(
                400,
                json=[
                    {
                        "error": {
                            "code": 400,
                            "status": "INVALID_ARGUMENT",
                            "message": "Invalid JSON payload: unknown field in response_schema",
                        }
                    }
                ],
            )
        return httpx.Response(200, json=OK_REPLY)

    provider = google_provider(handler, [])
    llm = StructuredLLM(provider)
    for _ in range(2):
        result = await llm.structured(
            purpose="p",
            prompt_version="v",
            system="sys",
            messages=[{"role": "user", "content": "q"}],
            schema=Answer,
        )
        assert result.value.value == 1
    assert [b["response_format"]["type"] for b in bodies] == [
        "json_schema",
        "json_object",
        "json_object",
    ]
    assert '"label"' in bodies[1]["messages"][0]["content"]  # schema moved into the prompt
    assert "title" not in json.dumps(bodies[0]["response_format"]["json_schema"]["schema"])
