"""Application configuration loaded from environment variables and `.env`."""

from functools import lru_cache
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Typed runtime settings for ForgeAI."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    app_env: Annotated[str, Field(default="development")]
    log_level: Annotated[str, Field(default="INFO")]
    api_host: Annotated[str, Field(default="0.0.0.0")]  # noqa: S104
    api_port: Annotated[int, Field(default=8000, ge=1, le=65535)]
    cors_origins: Annotated[
        list[str], NoDecode, Field(default_factory=lambda: ["http://localhost:3000"])
    ]

    # LLM Providers
    groq_api_key: Annotated[str, Field(default="")]
    gemini_api_key: Annotated[str, Field(default="")]
    nvidia_api_key: Annotated[str, Field(default="")]
    cloudflare_account_id: Annotated[str, Field(default="")]
    cloudflare_api_token: Annotated[
        str,
        Field(
            default="",
            validation_alias=AliasChoices("cloudflare_api_token", "cloudflare_api_key"),
        ),
    ]

    # LiteLLM Gateway
    litellm_base_url: Annotated[str, Field(default="http://localhost:4000")]
    litellm_master_key: Annotated[str, Field(default="")]

    # Supabase Cloud
    supabase_url: Annotated[str, Field(default="")]
    supabase_anon_key: Annotated[str, Field(default="")]
    supabase_service_role_key: Annotated[str, Field(default="")]
    supabase_jwt_secret: Annotated[str, Field(default="")]
    supabase_storage_bucket: Annotated[str, Field(default="forge-documents")]

    # ForgeAI Pipeline Guardrails
    forge_max_iterations: Annotated[int, Field(default=3, ge=1, le=10)]
    forge_max_llm_calls_per_run: Annotated[int, Field(default=120, ge=1)]
    forge_max_tokens_per_run: Annotated[int, Field(default=150000, ge=1000)]
    forge_early_stop_min_delta: Annotated[float, Field(default=0.02, ge=0.0, le=1.0)]
    forge_cache_ttl_seconds: Annotated[int, Field(default=3600, ge=0)]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def cloudflare_api_key(self) -> str:
        """Fallback alias property for callers expecting `cloudflare_api_key`."""
        return self.cloudflare_api_token


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton Settings instance."""
    return Settings()
