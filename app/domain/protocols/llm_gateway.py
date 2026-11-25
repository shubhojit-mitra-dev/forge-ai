"""LLM and embedding gateway protocol definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True, frozen=True)
class LLMResponse:
    """Immutable value object representing a single LLM completion response."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


@runtime_checkable
class LLMGatewayProtocol(Protocol):
    """Port for text completion via configured model tiers."""

    async def complete(
        self,
        messages: list[dict[str, str]],
        tier: str = "orchestrator-primary",
        temperature: float = 0.0,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Generate a completion for the given chat messages."""
        ...


@runtime_checkable
class EmbeddingGatewayProtocol(Protocol):
    """Port for generating dense vector embeddings from text."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input string."""
        ...
