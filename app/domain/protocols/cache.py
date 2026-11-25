"""Cache protocol definition."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CacheProtocol(Protocol):
    """Port for key-value caching with optional TTL expiration."""

    def get(self, key: str) -> Any | None:
        """Retrieve a cached value by key, or None if missing or expired."""
        ...

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Store a value under key with an optional TTL in seconds."""
        ...

    def delete(self, key: str) -> None:
        """Remove a key from the cache if present."""
        ...
