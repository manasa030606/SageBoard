"""Build the configured LLM from settings.

``LLM_PROVIDER=mock`` deliberately builds **nothing** (D42). The runtime never invents
model answers: with no real provider configured, analysis sessions stay queued with an
explanation. Scripted model replies exist only inside the test suite, where they drive
the real graph, the real SQL Guard and (in integration tests) the real database.
"""

from __future__ import annotations

from typing import Any

from app.agent.llm.client import LLMProvider, StructuredLLM
from app.agent.llm.providers import (
    GEMINI_OPENAI_BASE_URL,
    AnthropicProvider,
    OpenAICompatibleProvider,
    RequestPacer,
)
from app.core.config import LLMProvider as ProviderName
from app.core.config import Settings

DEFAULT_BASE_URLS = {
    ProviderName.ANTHROPIC: "https://api.anthropic.com",
    ProviderName.OPENAI: "https://api.openai.com/v1",
    ProviderName.GOOGLE: GEMINI_OPENAI_BASE_URL,
}

NOT_CONFIGURED_MESSAGE = (
    "No language model is configured (LLM_PROVIDER=mock), so Sageboard can’t analyse "
    "questions yet. Set LLM_PROVIDER, LLM_MODEL and the provider’s API key in apps/api/.env."
)


def build_provider(settings: Settings) -> LLMProvider | None:
    name = settings.llm_provider
    if name is ProviderName.MOCK:
        return None
    key_field = {
        ProviderName.ANTHROPIC: settings.anthropic_api_key,
        ProviderName.OPENAI: settings.openai_api_key,
        ProviderName.GOOGLE: settings.google_api_key,
    }[name]
    if key_field is None or not settings.llm_model:  # settings validation prevents this
        raise ValueError(f"LLM_PROVIDER={name.value} needs an API key and LLM_MODEL")
    common: dict[str, Any] = {
        "api_key": key_field.get_secret_value(),
        "model": settings.llm_model,
        "base_url": settings.llm_base_url or DEFAULT_BASE_URLS[name],
        "timeout_s": settings.llm_timeout_seconds,
        "max_output_tokens": settings.llm_max_output_tokens,
        "send_temperature": settings.llm_send_temperature,
        "reasoning_effort": settings.llm_reasoning_effort,
        # One pacer per app: every run in this process shares the per-minute budget.
        "pacer": RequestPacer(settings.llm_requests_per_minute),
    }
    if name is ProviderName.ANTHROPIC:
        return AnthropicProvider(**common)
    return OpenAICompatibleProvider(provider_name=name.value, **common)


def build_llm(settings: Settings) -> StructuredLLM | None:
    provider = build_provider(settings)
    return StructuredLLM(provider) if provider else None
