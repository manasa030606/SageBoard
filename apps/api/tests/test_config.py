from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.core.config import Environment, LLMProvider, Settings


def test_defaults_are_safe_for_development(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory()
    assert settings.llm_provider is LLMProvider.MOCK
    assert settings.cors_origins == ["http://localhost:3000"]
    assert settings.database_url is None


def test_cors_origins_parse_from_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, http://127.0.0.1:3000/")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]


@pytest.mark.parametrize("origin", ["*", "localhost:3000"])
def test_invalid_cors_origins_are_rejected(
    settings_factory: Callable[..., Settings], origin: str
) -> None:
    with pytest.raises(ValidationError):
        settings_factory(cors_origins=[origin])


def test_production_rejects_http_origins(settings_factory: Callable[..., Settings]) -> None:
    with pytest.raises(ValidationError, match="https"):
        settings_factory(
            env="production",
            cors_origins=["http://app.example.com"],
            llm_provider="openai",
            openai_api_key="sk-test",
            llm_model="some-model",
        )


def test_mock_llm_is_refused_in_production(settings_factory: Callable[..., Settings]) -> None:
    with pytest.raises(ValidationError, match="mock"):
        settings_factory(env="production", cors_origins=["https://app.example.com"])


@pytest.mark.parametrize(
    ("provider", "key_field"),
    [
        ("anthropic", "anthropic_api_key"),
        ("openai", "openai_api_key"),
        ("gemini", "gemini_api_key"),
    ],
)
def test_real_provider_requires_its_key_and_model(
    settings_factory: Callable[..., Settings], provider: str, key_field: str
) -> None:
    with pytest.raises(ValidationError, match=key_field.upper()):
        settings_factory(llm_provider=provider, llm_model="m")
    with pytest.raises(ValidationError, match="LLM_MODEL"):
        settings_factory(llm_provider=provider, **{key_field: "k"})

    settings = settings_factory(llm_provider=provider, llm_model="m", **{key_field: "k"})
    assert settings.llm_provider.value == provider


def test_database_url_must_use_async_driver(settings_factory: Callable[..., Settings]) -> None:
    with pytest.raises(ValidationError, match="asyncpg"):
        settings_factory(database_url="postgresql://u:p@localhost/db")
    ok = settings_factory(database_url="postgresql+asyncpg://u:p@localhost/db")
    assert ok.database_url is not None


def test_empty_database_url_means_not_configured(
    settings_factory: Callable[..., Settings],
) -> None:
    assert settings_factory(database_url="").database_url is None


def test_secrets_are_not_exposed_in_repr(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory(
        database_url="postgresql+asyncpg://user:hunter2@localhost/db",
        llm_provider="anthropic",
        anthropic_api_key="sk-ant-very-secret",
        llm_model="m",
    )
    dumped = repr(settings) + str(settings.model_dump())
    assert "hunter2" not in dumped
    assert "sk-ant-very-secret" not in dumped


def test_environment_enum_values() -> None:
    assert {e.value for e in Environment} == {"development", "test", "production"}
