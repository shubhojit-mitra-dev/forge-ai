"""LiteLLM gateway adapter implementing LLMGatewayProtocol."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import litellm
import structlog

from app.domain.protocols.llm_gateway import LLMResponse

logger = structlog.get_logger(__name__)

FAST_JUDGE_TIER = "fast-judge"
PROMOTED_TIER = "orchestrator-primary"
FAST_JUDGE_TPM_GUARD_TOKENS = 2800


def _estimate_tokens(messages: list[dict[str, str]]) -> int:
    return sum(len(m.get("content", "")) for m in messages) // 4


def _apply_tpm_preflight_guard(messages: list[dict[str, str]], tier: str) -> str:
    if tier == FAST_JUDGE_TIER and _estimate_tokens(messages) > FAST_JUDGE_TPM_GUARD_TOKENS:
        logger.info(
            "tpm_preflight_guard_promoted",
            from_tier=tier,
            to_tier=PROMOTED_TIER,
            estimated_tokens=_estimate_tokens(messages),
        )
        return PROMOTED_TIER
    return tier


class LiteLLMAdapter:
    """LLM gateway routing through LiteLLM proxy or direct litellm.acompletion."""

    def __init__(
        self,
        litellm_base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 45.0,
        max_retries: int = 3,
        base_backoff_seconds: float = 1.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = litellm_base_url.rstrip("/") if litellm_base_url else None
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._base_backoff_seconds = base_backoff_seconds
        self._http_client = http_client

    async def complete(
        self,
        messages: list[dict[str, str]],
        tier: str = "orchestrator-primary",
        temperature: float = 0.0,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Generate a completion for the given chat messages."""
        effective_tier = _apply_tpm_preflight_guard(messages, tier)
        started_at = time.monotonic()

        if self._base_url:
            return await self._complete_via_proxy(
                messages=messages,
                tier=effective_tier,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                started_at=started_at,
            )

        return await self._complete_direct(
            messages=messages,
            tier=effective_tier,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            started_at=started_at,
        )

    async def _complete_via_proxy(
        self,
        messages: list[dict[str, str]],
        tier: str,
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any] | None,
        started_at: float,
    ) -> LLMResponse:
        assert self._base_url is not None
        url = f"{self._base_url}/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload: dict[str, Any] = {
            "model": tier,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        response = await self._post_with_retry(url=url, headers=headers, payload=payload)
        data = response.json()
        choices = data.get("choices") or []
        message_obj = choices[0].get("message", {}) if choices else {}
        content = str(message_obj.get("content") or "")
        usage = data.get("usage") or {}
        elapsed_ms = int((time.monotonic() - started_at) * 1000)

        return LLMResponse(
            content=content,
            model=str(data.get("model") or tier),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=elapsed_ms,
        )

    async def _post_with_retry(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            if self._http_client is not None:
                response = await self._http_client.post(url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=payload)

            if response.status_code != 429:
                response.raise_for_status()
                return response

            if attempt >= self._max_retries:
                response.raise_for_status()

            delay = self._compute_backoff(response, attempt)
            logger.warning(
                "litellm_rate_limited_retrying",
                attempt=attempt + 1,
                delay_seconds=delay,
            )
            await asyncio.sleep(delay)

        raise RuntimeError("Unreachable retry loop termination")  # pragma: no cover

    def _compute_backoff(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        return self._base_backoff_seconds * float(2**attempt)

    async def _complete_direct(
        self,
        messages: list[dict[str, str]],
        tier: str,
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any] | None,
        started_at: float,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": tier,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        raw: Any = await litellm.acompletion(**kwargs)
        choices = getattr(raw, "choices", None) or []
        content = ""
        if choices:
            message = getattr(choices[0], "message", None)
            content = str(getattr(message, "content", "") or "")
        usage = getattr(raw, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        elapsed_ms = int((time.monotonic() - started_at) * 1000)

        return LLMResponse(
            content=content,
            model=str(getattr(raw, "model", None) or tier),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=elapsed_ms,
        )
