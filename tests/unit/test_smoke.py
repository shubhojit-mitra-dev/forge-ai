"""Smoke tests for ForgeAI environment, configuration, and Python version."""

import sys

import pytest

from app.config import Settings, get_settings


@pytest.mark.unit
def test_python_version_at_least_3_12() -> None:
    """Verify runtime Python version meets >= 3.12 requirement."""
    assert sys.version_info >= (3, 12)


@pytest.mark.unit
def test_get_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Settings loads expected defaults when env vars are unset."""
    get_settings.cache_clear()
    for var in (
        "APP_ENV",
        "LOG_LEVEL",
        "API_HOST",
        "API_PORT",
        "CORS_ORIGINS",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_API_KEY",
        "FORGE_MAX_ITERATIONS",
        "FORGE_MAX_LLM_CALLS_PER_RUN",
        "FORGE_MAX_TOKENS_PER_RUN",
        "FORGE_EARLY_STOP_MIN_DELTA",
        "FORGE_CACHE_TTL_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.api_host == "0.0.0.0"  # noqa: S104
    assert settings.api_port == 8000
    assert settings.cors_origins == ["http://localhost:3000"]
    assert settings.supabase_storage_bucket == "forge-documents"
    assert settings.forge_max_iterations == 3
    assert settings.forge_max_llm_calls_per_run == 120
    assert settings.forge_max_tokens_per_run == 150000
    assert settings.forge_early_stop_min_delta == pytest.approx(0.02)
    assert settings.forge_cache_ttl_seconds == 3600


@pytest.mark.unit
def test_get_settings_is_cached() -> None:
    """Verify get_settings returns the same cached instance across calls."""
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
    get_settings.cache_clear()


@pytest.mark.unit
def test_cloudflare_api_key_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLOUDFLARE_API_KEY works as a fallback for cloudflare_api_token."""
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "cf-fallback-secret")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cloudflare_api_token == "cf-fallback-secret"
    assert settings.cloudflare_api_key == "cf-fallback-secret"


@pytest.mark.unit
def test_cloudflare_api_token_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLOUDFLARE_API_TOKEN takes precedence and populates cloudflare_api_key."""
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-primary-token")
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "cf-fallback-secret")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cloudflare_api_token == "cf-primary-token"
    assert settings.cloudflare_api_key == "cf-primary-token"


@pytest.mark.unit
def test_cors_origins_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify comma-separated CORS_ORIGINS env var parses into a clean list."""
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:3000, https://forge-ai.shubhojitmitra.com",
    )
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cors_origins == [
        "http://localhost:3000",
        "https://forge-ai.shubhojitmitra.com",
    ]
