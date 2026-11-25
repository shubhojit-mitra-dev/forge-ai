"""Thread-safe in-memory TTL cache implementing CacheProtocol."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any

from cachetools import TTLCache


class InMemoryTTLCache:
    """Thread-safe in-memory cache backed by cachetools.TTLCache and an RLock."""

    def __init__(self, maxsize: int = 1024, default_ttl_seconds: int = 3600) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        if default_ttl_seconds <= 0:
            raise ValueError("default_ttl_seconds must be positive")
        self._lock = threading.RLock()
        self._default_ttl_seconds = default_ttl_seconds
        self._cache: TTLCache[str, tuple[Any, float | None]] = TTLCache(
            maxsize=maxsize,
            ttl=float(default_ttl_seconds),
        )

    @staticmethod
    def make_key(*parts: Any) -> str:
        """Build a deterministic SHA-256 hex digest key from arbitrary parts."""
        serialized = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Any | None:
        """Retrieve a cached value by key, or None if missing or expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at is not None and time.monotonic() >= expires_at:
                self._cache.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Store a value under key with an optional per-entry TTL in seconds."""
        if ttl_seconds is not None and ttl_seconds <= 0:
            with self._lock:
                self._cache.pop(key, None)
            return

        expires_at = time.monotonic() + float(ttl_seconds) if ttl_seconds is not None else None
        with self._lock:
            self._cache[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        """Remove a key from the cache if present."""
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        with self._lock:
            self._cache.clear()
