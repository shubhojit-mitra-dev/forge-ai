"""Unit tests for LiteLLMAdapter."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app.domain.protocols.llm_gateway import LLMGatewayProtocol, LLMResponse
from app.infrastructure.llm.litellm_adapter import LiteLLMAdapter


@pytest.mark.unit
class TestLiteLLMAdapter:
    def test_implements_llm_gateway_protocol(self) -> None:
        adapter = LiteLLMAdapter(litellm_base_url="http://localhost:4000", api_key="sk-test")
        assert isinstance(adapter, LLMGatewayProtocol)

    @respx.mock
    async def test_complete_via_http_proxy(self) -> None:
        route = respx.post("http://localhost:4000/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "model": "gemini/gemini-2.5-flash-lite",
                    "choices": [{"message": {"content": "Hello from ForgeAI"}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 5},
                },
            )
        )

        adapter = LiteLLMAdapter(litellm_base_url="http://localhost:4000", api_key="sk-test")
        resp = await adapter.complete(
            messages=[{"role": "user", "content": "Say hello"}],
            tier="orchestrator-primary",
            temperature=0.2,
            max_tokens=512,
        )

        assert isinstance(resp, LLMResponse)
        assert resp.content == "Hello from ForgeAI"
        assert resp.model == "gemini/gemini-2.5-flash-lite"
        assert resp.prompt_tokens == 12
        assert resp.completion_tokens == 5
        assert resp.latency_ms >= 0
        assert route.called
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["model"] == "orchestrator-primary"
        assert sent_body["temperature"] == 0.2
        assert sent_body["max_tokens"] == 512

    @respx.mock
    async def test_tpm_preflight_guard_promotes_fast_judge_over_2800_tokens(self) -> None:
        route = respx.post("http://localhost:4000/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "model": "orchestrator-primary",
                    "choices": [{"message": {"content": "Promoted response"}}],
                    "usage": {"prompt_tokens": 2900, "completion_tokens": 10},
                },
            )
        )

        # > 2800 estimated tokens => > 2800 * 4 = 11200 chars
        large_content = "x" * 11_204
        adapter = LiteLLMAdapter(litellm_base_url="http://localhost:4000", api_key="sk-test")
        await adapter.complete(
            messages=[{"role": "user", "content": large_content}],
            tier="fast-judge",
        )

        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["model"] == "orchestrator-primary"

    @respx.mock
    async def test_tpm_preflight_guard_keeps_fast_judge_under_threshold(self) -> None:
        route = respx.post("http://localhost:4000/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "model": "fast-judge",
                    "choices": [{"message": {"content": "Fast judge response"}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 10},
                },
            )
        )

        small_content = "x" * 400
        adapter = LiteLLMAdapter(litellm_base_url="http://localhost:4000", api_key="sk-test")
        await adapter.complete(
            messages=[{"role": "user", "content": small_content}],
            tier="fast-judge",
        )

        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["model"] == "fast-judge"

    @respx.mock
    async def test_retry_with_exponential_backoff_on_429(self) -> None:
        route = respx.post("http://localhost:4000/chat/completions").mock(
            side_effect=[
                httpx.Response(429, json={"error": "rate_limited"}),
                httpx.Response(429, json={"error": "rate_limited"}),
                httpx.Response(
                    200,
                    json={
                        "model": "orchestrator-primary",
                        "choices": [{"message": {"content": "Recovered after 429"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                    },
                ),
            ]
        )

        adapter = LiteLLMAdapter(
            litellm_base_url="http://localhost:4000",
            api_key="sk-test",
            max_retries=3,
            base_backoff_seconds=0.01,
        )
        with patch(
            "app.infrastructure.llm.litellm_adapter.asyncio.sleep", new_callable=AsyncMock
        ) as sleep_mock:
            resp = await adapter.complete(
                messages=[{"role": "user", "content": "hi"}],
                tier="orchestrator-primary",
            )

        assert resp.content == "Recovered after 429"
        assert route.call_count == 3
        assert sleep_mock.await_count == 2
        sleep_mock.assert_any_await(0.01)
        sleep_mock.assert_any_await(0.02)

    @respx.mock
    async def test_raises_after_exhausting_429_retries(self) -> None:
        respx.post("http://localhost:4000/chat/completions").mock(
            return_value=httpx.Response(429, json={"error": "rate_limited"})
        )

        adapter = LiteLLMAdapter(
            litellm_base_url="http://localhost:4000",
            api_key="sk-test",
            max_retries=2,
            base_backoff_seconds=0.01,
        )
        with (
            patch("app.infrastructure.llm.litellm_adapter.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await adapter.complete(
                messages=[{"role": "user", "content": "hi"}],
                tier="orchestrator-primary",
            )

    async def test_direct_litellm_acompletion_fallback(self) -> None:
        fake_response = SimpleNamespace(
            model="gemini/gemini-2.5-flash-lite",
            choices=[SimpleNamespace(message=SimpleNamespace(content="Direct completion"))],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=8),
        )

        adapter = LiteLLMAdapter(litellm_base_url=None)
        with patch(
            "app.infrastructure.llm.litellm_adapter.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=fake_response,
        ) as mock_acompletion:
            resp = await adapter.complete(
                messages=[{"role": "user", "content": "x" * 12_000}],
                tier="fast-judge",
                response_format={"type": "json_object"},
            )

        assert resp.content == "Direct completion"
        assert resp.prompt_tokens == 20
        assert resp.completion_tokens == 8
        mock_acompletion.assert_awaited_once()
        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["model"] == "orchestrator-primary"
        assert call_kwargs["response_format"] == {"type": "json_object"}
