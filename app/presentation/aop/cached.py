"""Async caching AOP decorator backed by CacheProtocol."""

from __future__ import annotations

import functools
import hashlib
import json
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.domain.protocols.cache import CacheProtocol

P = ParamSpec("P")
R = TypeVar("R")


def _build_cache_key(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    """Build a deterministic SHA-256 cache key for a function invocation."""
    payload = {
        "fn": f"{func.__module__}.{func.__qualname__}",
        "args": args,
        "kwargs": kwargs,
    }
    serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def cached_llm_call(
    cache_getter: Callable[[], CacheProtocol],
    *,
    ttl_seconds: int | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Cache async LLM/service call results using the supplied CacheProtocol getter."""

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            cache = cache_getter()
            key = _build_cache_key(func, args, kwargs)
            cached_value = cache.get(key)
            if cached_value is not None:
                return cast("R", cached_value)

            result = await func(*args, **kwargs)
            if result is not None:
                cache.set(key, result, ttl_seconds=ttl_seconds)
            return result

        return wrapper

    return decorator
