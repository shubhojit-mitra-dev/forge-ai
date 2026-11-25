"""Supabase client factory with LRU caching."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from supabase import Client, create_client

from app.config import get_settings
from app.domain.exceptions import ValidationDomainError

if TYPE_CHECKING:
    from app.config import Settings


@lru_cache(maxsize=4)
def _build_supabase_client(url: str, key: str) -> Client:
    return create_client(url, key)


def get_supabase_client(settings: Settings | None = None) -> Client:
    """Return a cached Supabase client for the configured project URL and key."""
    cfg = settings or get_settings()
    key = cfg.supabase_service_role_key or cfg.supabase_anon_key
    if not cfg.supabase_url or not key:
        raise ValidationDomainError(
            "SUPABASE_CONFIG_MISSING",
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY must be configured.",
        )
    return _build_supabase_client(cfg.supabase_url, key)


def clear_supabase_client_cache() -> None:
    """Clear the cached Supabase client instances (primarily for testing)."""
    _build_supabase_client.cache_clear()
