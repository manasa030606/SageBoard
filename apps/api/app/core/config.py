"""Application settings.

All configuration comes from environment variables (optionally loaded from a local
``.env`` file that is never committed). Settings are validated once at startup so a
misconfigured deployment fails fast instead of failing on the first request.
"""

from __future__ import annotations

import tempfile
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LLMProvider(StrEnum):
    """LLM providers (adapters in ``app/agent/llm``).

    ``mock`` configures **no** model: questions stay queued (D42); refused in production.
    ``google`` is the Gemini API (Google AI Studio keys); ``gemini`` is accepted as an alias.
    """

    MOCK = "mock"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"


_PROVIDER_KEY_FIELD: dict[LLMProvider, str] = {
    LLMProvider.ANTHROPIC: "anthropic_api_key",
    LLMProvider.OPENAI: "openai_api_key",
    LLMProvider.GOOGLE: "google_api_key",
}


MIN_JWT_SECRET_BYTES = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Service ---------------------------------------------------------
    app_name: str = "sageboard-api"
    app_version: str = "0.1.0"
    env: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"
    log_json: bool = True
    api_prefix: str = "/api/v1"

    # --- HTTP / CORS -----------------------------------------------------
    # Comma-separated in the environment, e.g. "http://localhost:3000,http://127.0.0.1:3000".
    # NoDecode stops pydantic-settings from trying to parse the raw string as JSON.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # --- Database --------------------------------------------------------
    # Application-metadata connection (role: sageboard_app). Optional in Phase 1 so the
    # service can start without a database; /readyz reports it as not configured.
    database_url: SecretStr | None = None
    # Migration connection (role: sageboard_owner). On Neon this must be the DIRECT
    # (non-pooled) endpoint: migrations rely on session state the pooler discards.
    migration_database_url: SecretStr | None = None
    # Analytical credentials — separate from the application role (ADR-0002).
    # Ingestion (role: sageboard_ingest) creates per-dataset schemas and loads data.
    ingest_database_url: SecretStr | None = None
    # Read-only executor (role: sageboard_executor, NOINHERIT): may only SET ROLE into a
    # dataset's reader role inside a READ ONLY transaction.
    executor_database_url: SecretStr | None = None
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    db_connect_timeout_s: float = Field(default=5.0, gt=0, le=60)

    # --- Uploads & ingestion ---------------------------------------------
    upload_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1024, le=200 * 1024 * 1024)
    upload_max_rows: int = Field(default=1_000_000, ge=1)
    upload_max_columns: int = Field(default=200, ge=1, le=1600)
    # Directory for in-flight uploads. Files get random names and are deleted after use.
    upload_dir: Path = Field(
        default_factory=lambda: Path(tempfile.gettempdir()) / "sageboard-uploads"
    )
    upload_ttl_minutes: int = Field(default=60, ge=1)
    preview_max_rows: int = Field(default=100, ge=1, le=1000)
    # Size of the sample dataset each user can load from the Data page.
    demo_dataset_scale: Literal["small", "standard"] = "standard"
    executor_statement_timeout_ms: int = Field(default=10_000, ge=100, le=120_000)

    # --- Authentication ------------------------------------------------------
    # "session": real accounts (argon2id passwords, JWT access cookie + rotating refresh
    # cookie, CSRF double-submit). "demo": every request acts as the seeded demo user —
    # local development only; refused when ENV=production.
    auth_mode: Literal["session", "demo"] = "session"
    demo_user_email: str = "demo@sageboard.local"
    jwt_secret: SecretStr | None = None
    access_token_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_days: int = Field(default=14, ge=1, le=90)
    # Cookies. Same-site deployments (web and API on one registrable domain) use "lax".
    # Cross-site (e.g. *.vercel.app + *.onrender.com) needs "none", which requires Secure.
    cookie_secure: bool | None = None  # default: True in production, False otherwise
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None
    # Per-process rate limits (single API instance, ADR-0004).
    login_attempts_per_minute: int = Field(default=5, ge=1, le=1000)
    registrations_per_hour: int = Field(default=10, ge=1, le=10_000)
    uploads_per_hour: int = Field(default=20, ge=1, le=10_000)
    analyses_per_hour: int = Field(default=30, ge=1, le=10_000)  # each run spends LLM tokens

    # --- LLM ---------------------------------------------------------------------
    llm_provider: LLMProvider = LLMProvider.MOCK
    llm_model: str | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    # Google AI Studio key. GOOGLE_API_KEY is the documented name; GEMINI_API_KEY works too.
    google_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "google_api_key", "GOOGLE_API_KEY", "gemini_api_key", "GEMINI_API_KEY"
        ),
    )
    llm_base_url: str | None = None  # override, e.g. an OpenAI-compatible gateway
    llm_timeout_seconds: float = Field(default=60.0, ge=5, le=300)
    # Reasoning ("thinking") models spend part of this budget before answering.
    llm_max_output_tokens: int = Field(default=8192, ge=256, le=32_000)
    # OpenAI-compatible providers (Gemini, OpenAI): how much the model reasons per call.
    # "low" is faster and cheaper on quota; unset = the provider's default.
    llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = None
    # Some reasoning models reject a temperature parameter; set false for those.
    llm_send_temperature: bool = True

    # --- Agent budgets (per analysis session) --------------------------------
    agent_max_llm_calls: int = Field(default=30, ge=5, le=200)
    agent_max_sql_executions: int = Field(default=14, ge=1, le=100)
    agent_deadline_seconds: int = Field(default=180, ge=10, le=1800)
    agent_max_result_rows: int = Field(default=5000, ge=10, le=10_000)
    # Free-tier protection (D50). Requests per minute are paced client-side so a run
    # doesn't trip the provider's per-minute limit; the daily cap counts every model
    # call recorded today (midnight Pacific, when Google's daily quota resets) and stops
    # new questions once reached. 0 disables a limit.
    llm_requests_per_minute: int = Field(default=10, ge=0, le=10_000)
    llm_daily_request_limit: int = Field(default=200, ge=0, le=1_000_000)

    # ------------------------------------------------------------------ validators
    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip().rstrip("/") for o in value.split(",") if o.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _validate_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            if origin == "*":
                raise ValueError(
                    "Wildcard CORS origin is not allowed: the API uses credentialed requests."
                )
            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"CORS origin must include a scheme: {origin!r}")
        return origins

    @field_validator(
        "database_url", "migration_database_url", "ingest_database_url", "executor_database_url"
    )
    @classmethod
    def _validate_db_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or not value.get_secret_value().strip():
            return None
        url = value.get_secret_value()
        if not url.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the async driver: postgresql+asyncpg://...")
        return value

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _provider_alias(cls, value: object) -> object:
        return "google" if isinstance(value, str) and value.strip().lower() == "gemini" else value

    @model_validator(mode="after")
    def _validate_llm(self) -> Self:
        if self.llm_provider is LLMProvider.MOCK:
            if self.env is Environment.PRODUCTION:
                raise ValueError("LLM_PROVIDER=mock is not allowed when ENV=production.")
            return self
        key_field = _PROVIDER_KEY_FIELD[self.llm_provider]
        key: SecretStr | None = getattr(self, key_field)
        if key is None or not key.get_secret_value().strip():
            raise ValueError(
                f"LLM_PROVIDER={self.llm_provider.value} requires {key_field.upper()} to be set."
            )
        if not self.llm_model:
            raise ValueError(f"LLM_PROVIDER={self.llm_provider.value} requires LLM_MODEL.")
        return self

    @model_validator(mode="after")
    def _validate_production(self) -> Self:
        if self.env is Environment.PRODUCTION:
            insecure = [o for o in self.cors_origins if o.startswith("http://")]
            if insecure:
                raise ValueError(f"Production CORS origins must use https: {insecure}")
            if self.auth_mode == "demo":
                raise ValueError("AUTH_MODE=demo is not allowed when ENV=production.")
            if self.cookie_secure is False:
                raise ValueError("COOKIE_SECURE=false is not allowed when ENV=production.")
        return self

    @model_validator(mode="after")
    def _validate_auth(self) -> Self:
        if self.auth_mode == "session":
            secret = self.jwt_secret.get_secret_value() if self.jwt_secret else ""
            if len(secret.encode()) < MIN_JWT_SECRET_BYTES:
                raise ValueError(
                    f"AUTH_MODE=session requires JWT_SECRET of at least {MIN_JWT_SECRET_BYTES} bytes. "
                    'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
                )
        if self.cookie_samesite == "none" and not self.secure_cookies:
            raise ValueError("COOKIE_SAMESITE=none requires secure cookies (COOKIE_SECURE=true).")
        return self

    # ------------------------------------------------------------------ helpers
    @property
    def is_production(self) -> bool:
        return self.env is Environment.PRODUCTION

    @property
    def secure_cookies(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor, used as a FastAPI dependency and at startup."""
    return Settings()
