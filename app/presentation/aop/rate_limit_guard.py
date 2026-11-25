"""Exponential-backoff retry decorator for HTTP 429 / provider rate-limit errors."""

from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, ParamSpec, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

P = ParamSpec("P")
R = TypeVar("R")


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Return True if the exception represents an HTTP 429 or rate-limit failure."""
    if getattr(exc, "status_code", None) == 429:
        return True
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True
    if "ratelimit" in type(exc).__name__.lower():
        return True
    message = str(exc).lower()
    return "429" in message or "rate limit" in message or "rate_limit" in message


def with_rate_limit_backoff(
    max_retries: int = 3,
    base_delay: float = 0.5,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Retry async calls on 429/rate-limit errors with exponential backoff."""
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    if base_delay < 0.0:
        raise ValueError("base_delay must be non-negative")

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    if not _is_rate_limit_error(exc) or attempt >= max_retries:
                        raise
                    delay = base_delay * (2**attempt)
                    await asyncio.sleep(delay)
            raise AssertionError("Unreachable retry loop exit")  # pragma: no cover

        return wrapper

    return decorator
