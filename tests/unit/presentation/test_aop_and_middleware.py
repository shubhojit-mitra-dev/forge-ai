"""Unit tests for presentation AOP decorators, auth middleware, and exception handlers."""

from __future__ import annotations

import time
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.domain.exceptions import (
    BudgetExceededError,
    EntityNotFoundError,
    ForgeDomainError,
    GroundabilityBlockedError,
    InvalidToolSelectionError,
    ValidationDomainError,
)
from app.infrastructure.cache.ttl_cache import InMemoryTTLCache
from app.presentation.aop.cached import cached_llm_call
from app.presentation.aop.rate_limit_guard import with_rate_limit_backoff
from app.presentation.aop.telemetry import CorrelationIdMiddleware, timed_operation
from app.presentation.handlers.exception_handlers import (
    ProblemDetails,
    register_exception_handlers,
)
from app.presentation.middleware.auth import UserContext, get_current_user

TEST_JWT_SECRET = "super-secret-supabase-jwt-key-for-unit-tests-only"


class _FakeRateLimitError(Exception):
    """Fake exception carrying an HTTP 429 status_code attribute."""

    def __init__(self, message: str = "Too Many Requests", status_code: int = 429) -> None:
        super().__init__(message)
        self.status_code = status_code


@pytest.mark.unit
async def test_cached_llm_call_hits_and_misses() -> None:
    """Verify @cached_llm_call caches non-None results and distinguishes arguments."""
    cache = InMemoryTTLCache(maxsize=16, default_ttl_seconds=60)
    calls = 0

    @cached_llm_call(lambda: cache, ttl_seconds=120)
    async def generate(prompt: str, temperature: float = 0.0) -> str:
        nonlocal calls
        calls += 1
        return f"resp:{prompt}:{temperature}"

    first = await generate("hello", temperature=0.1)
    second = await generate("hello", temperature=0.1)
    third = await generate("world", temperature=0.1)

    assert first == "resp:hello:0.1"
    assert second == first
    assert third == "resp:world:0.1"
    assert calls == 2


@pytest.mark.unit
async def test_with_rate_limit_backoff_retries_and_succeeds() -> None:
    """Verify @with_rate_limit_backoff retries 429 errors with exponential backoff."""
    attempts = 0

    @with_rate_limit_backoff(max_retries=3, base_delay=0.25)
    async def flaky_call() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise _FakeRateLimitError("Rate limit exceeded", status_code=429)
        return "ok"

    with patch(
        "app.presentation.aop.rate_limit_guard.asyncio.sleep",
        new_callable=AsyncMock,
    ) as mock_sleep:
        result = await flaky_call()

    assert result == "ok"
    assert attempts == 3
    assert [call.args[0] for call in mock_sleep.await_args_list] == [0.25, 0.5]


@pytest.mark.unit
async def test_with_rate_limit_backoff_exhausts_retries() -> None:
    """Verify @with_rate_limit_backoff re-raises after max_retries exhausted."""
    attempts = 0

    @with_rate_limit_backoff(max_retries=2, base_delay=0.1)
    async def always_429() -> str:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("HTTP 429: rate limit reached")

    with (
        patch(
            "app.presentation.aop.rate_limit_guard.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep,
        pytest.raises(RuntimeError, match="429"),
    ):
        await always_429()

    assert attempts == 3
    assert [call.args[0] for call in mock_sleep.await_args_list] == [0.1, 0.2]


@pytest.mark.unit
async def test_with_rate_limit_backoff_does_not_retry_non_429() -> None:
    """Verify @with_rate_limit_backoff immediately propagates non-rate-limit errors."""
    attempts = 0

    @with_rate_limit_backoff(max_retries=3, base_delay=0.5)
    async def bad_input() -> str:
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid payload")

    with (
        patch(
            "app.presentation.aop.rate_limit_guard.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep,
        pytest.raises(ValueError, match="invalid payload"),
    ):
        await bad_input()

    assert attempts == 1
    mock_sleep.assert_not_awaited()


@pytest.mark.unit
async def test_timed_operation_logs_duration_and_returns_value() -> None:
    """Verify @timed_operation preserves return value and emits structured timing log."""
    mock_logger = MagicMock()

    @timed_operation("judge.score_case")
    async def score_case(x: int) -> int:
        return x * 2

    with patch("app.presentation.aop.telemetry.logger", mock_logger):
        result = await score_case(21)

    assert result == 42
    mock_logger.info.assert_called_once()
    event, kwargs = mock_logger.info.call_args[0][0], mock_logger.info.call_args[1]
    assert event == "operation.completed"
    assert kwargs["operation"] == "judge.score_case"
    assert isinstance(kwargs["duration_ms"], float)
    assert kwargs["duration_ms"] >= 0.0


@pytest.mark.unit
def test_correlation_id_middleware_generates_and_preserves_headers() -> None:
    """Verify CorrelationIdMiddleware adds X-Correlation-ID and X-Process-Time-Ms."""
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)

    res_generated = client.get("/ping")
    assert res_generated.status_code == 200
    generated_id = res_generated.headers["X-Correlation-ID"]
    assert str(UUID(generated_id)) == generated_id
    assert float(res_generated.headers["X-Process-Time-Ms"]) >= 0.0

    custom_id = "corr-12345-abc"
    res_preserved = client.get("/ping", headers={"X-Correlation-ID": custom_id})
    assert res_preserved.status_code == 200
    assert res_preserved.headers["X-Correlation-ID"] == custom_id
    assert float(res_preserved.headers["X-Process-Time-Ms"]) >= 0.0


def _build_auth_test_app() -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,  # type: ignore[call-arg]
        supabase_jwt_secret=TEST_JWT_SECRET,
    )

    @app.get("/protected")
    async def protected(
        user: Annotated[UserContext, Depends(get_current_user)],
    ) -> dict[str, str | None]:
        return {"user_id": str(user.user_id), "email": user.email}

    return app


@pytest.mark.unit
def test_auth_valid_hs256_jwt_returns_user_context() -> None:
    """Verify get_current_user decodes a valid Supabase HS256 JWT into UserContext."""
    uid = uuid4()
    token = jwt.encode(
        {
            "sub": str(uid),
            "email": "builder@forge.ai",
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )

    client = TestClient(_build_auth_test_app())
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"user_id": str(uid), "email": "builder@forge.ai"}


@pytest.mark.unit
def test_auth_missing_invalid_and_expired_tokens_return_401() -> None:
    """Verify missing, invalid, malformed-sub, or expired JWTs return HTTP 401."""
    client = TestClient(_build_auth_test_app())

    # Missing header
    assert client.get("/protected").status_code == 401

    # Invalid signature
    wrong_sig = jwt.encode(
        {"sub": str(uuid4()), "exp": int(time.time()) + 3600},
        "wrong-secret-key-that-is-at-least-32-bytes",
        algorithm="HS256",
    )
    assert (
        client.get("/protected", headers={"Authorization": f"Bearer {wrong_sig}"}).status_code
        == 401
    )

    # Expired token
    expired = jwt.encode(
        {"sub": str(uuid4()), "exp": int(time.time()) - 60},
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    assert (
        client.get("/protected", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    )

    # Non-UUID sub
    bad_sub = jwt.encode(
        {"sub": "not-a-uuid", "exp": int(time.time()) + 3600},
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    assert (
        client.get("/protected", headers={"Authorization": f"Bearer {bad_sub}"}).status_code == 401
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (EntityNotFoundError("PROJECT_NOT_FOUND", "Project missing"), 404),
        (GroundabilityBlockedError("UNGROUNDED_TOPIC", "Cannot ground billing"), 422),
        (BudgetExceededError("TOKEN_BUDGET_EXCEEDED", "Exceeded 150k tokens"), 429),
        (InvalidToolSelectionError("TOOL_NOT_ALLOWED", "weather_http not justified"), 400),
        (ValidationDomainError("INVALID_SCORE", "Score out of range"), 400),
        (ForgeDomainError("DOMAIN_ERROR", "Generic domain violation"), 400),
    ],
)
def test_domain_exception_handlers_map_to_problem_details(
    exc: ForgeDomainError,
    expected_status: int,
) -> None:
    """Verify ForgeDomainError subclasses map to RFC 7807 ProblemDetails JSON."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise exc

    client = TestClient(app)
    response = client.get("/boom")

    assert response.status_code == expected_status
    assert response.headers["content-type"].startswith("application/problem+json")

    payload = ProblemDetails.model_validate(response.json())
    assert payload.status == expected_status
    assert payload.code == exc.code
    assert payload.detail == exc.detail
    assert payload.title
    assert payload.type.endswith(exc.code)
