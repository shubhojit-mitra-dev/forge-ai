"""Cloudflare Workers AI embeddings adapter implementing EmbeddingGatewayProtocol."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

CLOUDFLARE_BGE_MODEL = "@cf/baai/bge-base-en-v1.5"
MAX_BATCH_SIZE = 50
EMBEDDING_DIM = 768


class CloudflareEmbeddingsAdapter:
    """Generates 768-dim BGE embeddings via Cloudflare Workers AI."""

    def __init__(
        self,
        account_id: str,
        api_token: str,
        batch_size: int = MAX_BATCH_SIZE,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        base_backoff_seconds: float = 1.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not 1 <= batch_size <= MAX_BATCH_SIZE:
            raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
        self._url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
            f"/ai/run/{CLOUDFLARE_BGE_MODEL}"
        )
        self._api_token = api_token
        self._batch_size = batch_size
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._base_backoff_seconds = base_backoff_seconds
        self._http_client = http_client

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one 768-dim embedding vector per input string."""
        if not texts:
            return []

        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors = await self._embed_batch(batch)
            all_vectors.extend(vectors)
        return all_vectors

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {"text": batch}
        response = await self._post_with_retry(headers=headers, payload=payload)
        body = response.json()

        if not body.get("success", False):
            raise RuntimeError(f"Cloudflare embeddings API returned failure: {body}")

        result = body.get("result") or {}
        raw_data = result.get("data") or []
        vectors: list[list[float]] = [[float(x) for x in vec] for vec in raw_data]

        if len(vectors) != len(batch):
            raise RuntimeError(f"Expected {len(batch)} embedding vectors, got {len(vectors)}")
        for vec in vectors:
            if len(vec) != EMBEDDING_DIM:
                raise RuntimeError(f"Expected {EMBEDDING_DIM}-dim vector, got {len(vec)}")
        return vectors

    async def _post_with_retry(
        self,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            if self._http_client is not None:
                response = await self._http_client.post(self._url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(self._url, headers=headers, json=payload)

            if response.status_code != 429:
                response.raise_for_status()
                return response

            if attempt >= self._max_retries:
                response.raise_for_status()

            delay = self._base_backoff_seconds * float(2**attempt)
            logger.warning(
                "cloudflare_embeddings_rate_limited_retrying",
                attempt=attempt + 1,
                delay_seconds=delay,
            )
            await asyncio.sleep(delay)

        raise RuntimeError("Unreachable retry loop termination")  # pragma: no cover
