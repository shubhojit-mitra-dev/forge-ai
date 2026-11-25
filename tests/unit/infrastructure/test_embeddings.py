"""Unit tests for CloudflareEmbeddingsAdapter."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app.domain.protocols.llm_gateway import EmbeddingGatewayProtocol
from app.infrastructure.llm.embeddings import CloudflareEmbeddingsAdapter


def _make_vector(seed: int, dim: int = 768) -> list[float]:
    return [float(seed) * 0.001 + float(i) * 0.0001 for i in range(dim)]


@pytest.mark.unit
class TestCloudflareEmbeddingsAdapter:
    def test_implements_embedding_gateway_protocol(self) -> None:
        adapter = CloudflareEmbeddingsAdapter(account_id="acc-123", api_token="tok-abc")
        assert isinstance(adapter, EmbeddingGatewayProtocol)

    @respx.mock
    async def test_embed_empty_list_returns_empty(self) -> None:
        adapter = CloudflareEmbeddingsAdapter(account_id="acc-123", api_token="tok-abc")
        result = await adapter.embed_texts([])
        assert result == []

    @respx.mock
    async def test_embed_texts_single_batch_768_dim(self) -> None:
        url = (
            "https://api.cloudflare.com/client/v4/accounts/acc-123/ai/run/@cf/baai/bge-base-en-v1.5"
        )
        route = respx.post(url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {
                        "shape": [2, 768],
                        "data": [_make_vector(1), _make_vector(2)],
                    },
                },
            )
        )

        adapter = CloudflareEmbeddingsAdapter(account_id="acc-123", api_token="tok-abc")
        vectors = await adapter.embed_texts(["alpha", "beta"])

        assert len(vectors) == 2
        assert len(vectors[0]) == 768
        assert len(vectors[1]) == 768
        assert route.call_count == 1
        sent = json.loads(route.calls[0].request.content)
        assert sent == {"text": ["alpha", "beta"]}

    @respx.mock
    async def test_embed_texts_splits_into_batches_of_50(self) -> None:
        url = (
            "https://api.cloudflare.com/client/v4/accounts/acc-123/ai/run/@cf/baai/bge-base-en-v1.5"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            batch = payload["text"]
            data = [_make_vector(idx) for idx, _ in enumerate(batch)]
            return httpx.Response(
                200,
                json={"success": True, "result": {"shape": [len(batch), 768], "data": data}},
            )

        route = respx.post(url).mock(side_effect=handler)

        texts = [f"chunk-{i}" for i in range(120)]
        adapter = CloudflareEmbeddingsAdapter(account_id="acc-123", api_token="tok-abc")
        vectors = await adapter.embed_texts(texts)

        assert len(vectors) == 120
        assert all(len(v) == 768 for v in vectors)
        assert route.call_count == 3
        assert len(json.loads(route.calls[0].request.content)["text"]) == 50
        assert len(json.loads(route.calls[1].request.content)["text"]) == 50
        assert len(json.loads(route.calls[2].request.content)["text"]) == 20

    @respx.mock
    async def test_embed_texts_retries_on_429(self) -> None:
        url = (
            "https://api.cloudflare.com/client/v4/accounts/acc-123/ai/run/@cf/baai/bge-base-en-v1.5"
        )
        route = respx.post(url).mock(
            side_effect=[
                httpx.Response(429, json={"success": False}),
                httpx.Response(
                    200,
                    json={
                        "success": True,
                        "result": {"shape": [1, 768], "data": [_make_vector(7)]},
                    },
                ),
            ]
        )

        adapter = CloudflareEmbeddingsAdapter(
            account_id="acc-123",
            api_token="tok-abc",
            max_retries=2,
            base_backoff_seconds=0.01,
        )
        with patch("app.infrastructure.llm.embeddings.asyncio.sleep", new_callable=AsyncMock):
            vectors = await adapter.embed_texts(["retry me"])

        assert len(vectors) == 1
        assert len(vectors[0]) == 768
        assert route.call_count == 2
