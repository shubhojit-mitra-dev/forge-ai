"""Unit tests for InMemoryTTLCache."""

from __future__ import annotations

import threading
import time

import pytest

from app.domain.protocols.cache import CacheProtocol
from app.infrastructure.cache.ttl_cache import InMemoryTTLCache


@pytest.mark.unit
class TestInMemoryTTLCache:
    def test_implements_cache_protocol(self) -> None:
        cache = InMemoryTTLCache(maxsize=100, default_ttl_seconds=60)
        assert isinstance(cache, CacheProtocol)

    def test_set_and_get_roundtrip(self) -> None:
        cache = InMemoryTTLCache(maxsize=100, default_ttl_seconds=60)
        cache.set("key-1", {"answer": 42})
        assert cache.get("key-1") == {"answer": 42}

    def test_get_missing_returns_none(self) -> None:
        cache = InMemoryTTLCache(maxsize=100, default_ttl_seconds=60)
        assert cache.get("nonexistent") is None

    def test_delete_removes_key(self) -> None:
        cache = InMemoryTTLCache(maxsize=100, default_ttl_seconds=60)
        cache.set("key-1", "value")
        cache.delete("key-1")
        assert cache.get("key-1") is None

    def test_delete_missing_key_is_noop(self) -> None:
        cache = InMemoryTTLCache(maxsize=100, default_ttl_seconds=60)
        cache.delete("does-not-exist")

    def test_per_item_ttl_expiry(self) -> None:
        cache = InMemoryTTLCache(maxsize=100, default_ttl_seconds=3600)
        cache.set("short-lived", "hello", ttl_seconds=0)
        assert cache.get("short-lived") is None

        cache.set("brief", "world", ttl_seconds=1)
        assert cache.get("brief") == "world"
        time.sleep(1.05)
        assert cache.get("brief") is None

    def test_make_key_is_deterministic_sha256(self) -> None:
        k1 = InMemoryTTLCache.make_key("orchestrator-primary", "hello", 0.0)
        k2 = InMemoryTTLCache.make_key("orchestrator-primary", "hello", 0.0)
        k3 = InMemoryTTLCache.make_key("orchestrator-primary", "hello", 0.5)
        assert k1 == k2
        assert k1 != k3
        assert len(k1) == 64

    def test_thread_safe_concurrent_reads_and_writes(self) -> None:
        cache = InMemoryTTLCache(maxsize=500, default_ttl_seconds=60)
        errors: list[Exception] = []

        def worker(worker_id: int) -> None:
            try:
                for i in range(50):
                    key = f"w-{worker_id}-{i}"
                    cache.set(key, i)
                    _ = cache.get(key)
                    if i % 5 == 0:
                        cache.delete(key)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(w,)) for w in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
