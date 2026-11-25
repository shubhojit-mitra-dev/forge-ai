"""Structured operation timing decorator and HTTP correlation ID middleware."""

from __future__ import annotations

import functools
import inspect
import time
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response

P = ParamSpec("P")
R = TypeVar("R")

logger = structlog.get_logger("forge.telemetry")


def timed_operation(op_name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Log execution duration in milliseconds for sync or async operations."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                start = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                except Exception as exc:
                    elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
                    logger.warning(
                        "operation.failed",
                        operation=op_name,
                        duration_ms=elapsed_ms,
                        error_type=type(exc).__name__,
                    )
                    raise
                elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
                logger.info(
                    "operation.completed",
                    operation=op_name,
                    duration_ms=elapsed_ms,
                )
                return result

            return cast("Callable[P, R]", async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
                logger.warning(
                    "operation.failed",
                    operation=op_name,
                    duration_ms=elapsed_ms,
                    error_type=type(exc).__name__,
                )
                raise
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            logger.info(
                "operation.completed",
                operation=op_name,
                duration_ms=elapsed_ms,
            )
            return result

        return sync_wrapper

    return decorator


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach X-Correlation-ID and X-Process-Time-Ms headers to every HTTP response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Bind correlation ID for the request lifecycle and record processing time."""
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
        request.state.correlation_id = correlation_id
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("correlation_id")

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        return response
