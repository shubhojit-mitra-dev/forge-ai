"""Unit tests for domain Protocol structural conformance."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.domain.protocols import (
    AgentRepositoryProtocol,
    AgentToolProtocol,
    CacheProtocol,
    ChatRepositoryProtocol,
    DocumentParserProtocol,
    DocumentRepositoryProtocol,
    EmbeddingGatewayProtocol,
    EvalRepositoryProtocol,
    LLMGatewayProtocol,
    LLMResponse,
    ProjectRepositoryProtocol,
    VectorStoreProtocol,
)


class DummyLLMGateway:
    """Minimal structural implementation of LLMGatewayProtocol."""

    async def complete(
        self,
        messages: list[dict[str, str]],
        tier: str = "orchestrator-primary",
        temperature: float = 0.0,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            content="ok",
            model=tier,
            prompt_tokens=len(messages),
            completion_tokens=1,
            latency_ms=10,
        )


class DummyEmbeddingGateway:
    """Minimal structural implementation of EmbeddingGatewayProtocol."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]


class DummyVectorStore:
    """Minimal structural implementation of VectorStoreProtocol."""

    async def upsert_chunks(self, chunks: list[Any]) -> None:
        return None

    async def hybrid_search(
        self,
        project_id: UUID,
        query_text: str,
        query_embedding: list[float],
        top_k: int = 5,
        similarity_threshold: float = 0.35,
    ) -> list[Any]:
        return []


class DummyDocumentParser:
    """Minimal structural implementation of DocumentParserProtocol."""

    def supports(self, mime_type: str, filename: str) -> bool:
        return mime_type == "text/plain" or filename.endswith(".txt")

    def parse(self, content: bytes, filename: str) -> str:
        return content.decode("utf-8")


class DummyAgentTool:
    """Minimal structural implementation of AgentToolProtocol."""

    @property
    def name(self) -> Any:
        return "calculator"

    @property
    def description(self) -> str:
        return "Evaluates arithmetic expressions."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"expr": {"type": "string"}}}

    async def execute(self, **kwargs: Any) -> str:
        return str(kwargs.get("expr", ""))


class DummyCache:
    """Minimal structural implementation of CacheProtocol."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        return self._store.get(key)

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        self._store[key] = value

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


class DummyProjectRepository:
    """Minimal structural implementation of ProjectRepositoryProtocol."""

    async def create(self, project: Any) -> Any:
        return project

    async def get_by_id(self, project_id: UUID) -> Any | None:
        return None

    async def list_by_user(self, user_id: UUID) -> list[Any]:
        return []

    async def update(self, project: Any) -> Any:
        return project


class DummyDocumentRepository:
    """Minimal structural implementation of DocumentRepositoryProtocol."""

    async def create(self, document: Any) -> Any:
        return document

    async def get_by_id(self, document_id: UUID) -> Any | None:
        return None

    async def list_by_project(self, project_id: UUID) -> list[Any]:
        return []

    async def get_by_hash(self, project_id: UUID, content_hash: str) -> Any | None:
        return None


class DummyAgentRepository:
    """Minimal structural implementation of AgentRepositoryProtocol."""

    async def save(self, agent: Any) -> Any:
        return agent

    async def get_latest(self, project_id: UUID) -> Any | None:
        return None

    async def get_by_slug(self, slug: str) -> Any | None:
        return None

    async def list_versions(self, project_id: UUID) -> list[Any]:
        return []


class DummyEvalRepository:
    """Minimal structural implementation of EvalRepositoryProtocol."""

    async def save_eval_cases(self, project_id: UUID, cases: list[Any]) -> None:
        return None

    async def list_eval_cases(self, project_id: UUID) -> list[Any]:
        return []

    async def save_judge_scores(self, project_id: UUID, iteration: int, scores: list[Any]) -> None:
        return None

    async def save_iteration_log(self, project_id: UUID, log: Any) -> None:
        return None

    async def list_iteration_logs(self, project_id: UUID) -> list[Any]:
        return []

    async def save_honest_report(self, report: Any) -> None:
        return None

    async def get_honest_report(self, project_id: UUID) -> Any | None:
        return None


class DummyChatRepository:
    """Minimal structural implementation of ChatRepositoryProtocol."""

    async def create_conversation(self, conversation: Any) -> Any:
        return conversation

    async def get_conversation(self, conversation_id: UUID) -> Any | None:
        return None

    async def add_message(self, message: Any) -> Any:
        return message

    async def list_messages(self, conversation_id: UUID) -> list[Any]:
        return []


class IncompleteObject:
    """Object that does not satisfy any domain protocol."""


@pytest.mark.unit
def test_llm_response_is_frozen_dataclass() -> None:
    response = LLMResponse(
        content="hello",
        model="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms=42,
    )
    assert response.content == "hello"
    assert response.model == "gpt-4o-mini"
    assert response.prompt_tokens == 10
    assert response.completion_tokens == 5
    assert response.latency_ms == 42

    with pytest.raises(FrozenInstanceError):
        response.content = "mutated"  # type: ignore[misc]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("instance", "protocol"),
    [
        (DummyLLMGateway(), LLMGatewayProtocol),
        (DummyEmbeddingGateway(), EmbeddingGatewayProtocol),
        (DummyVectorStore(), VectorStoreProtocol),
        (DummyDocumentParser(), DocumentParserProtocol),
        (DummyAgentTool(), AgentToolProtocol),
        (DummyCache(), CacheProtocol),
        (DummyProjectRepository(), ProjectRepositoryProtocol),
        (DummyDocumentRepository(), DocumentRepositoryProtocol),
        (DummyAgentRepository(), AgentRepositoryProtocol),
        (DummyEvalRepository(), EvalRepositoryProtocol),
        (DummyChatRepository(), ChatRepositoryProtocol),
    ],
)
def test_runtime_checkable_protocols_accept_conforming_dummies(
    instance: object,
    protocol: type[Any],
) -> None:
    assert isinstance(instance, protocol)


@pytest.mark.unit
@pytest.mark.parametrize(
    "protocol",
    [
        LLMGatewayProtocol,
        EmbeddingGatewayProtocol,
        VectorStoreProtocol,
        DocumentParserProtocol,
        AgentToolProtocol,
        CacheProtocol,
        ProjectRepositoryProtocol,
        DocumentRepositoryProtocol,
        AgentRepositoryProtocol,
        EvalRepositoryProtocol,
        ChatRepositoryProtocol,
    ],
)
def test_runtime_checkable_protocols_reject_incomplete_object(
    protocol: type[Any],
) -> None:
    assert not isinstance(IncompleteObject(), protocol)


@pytest.mark.unit
async def test_dummy_protocol_invocations() -> None:
    gateway = DummyLLMGateway()
    res = await gateway.complete([{"role": "user", "content": "hi"}])
    assert res.content == "ok"

    embedder = DummyEmbeddingGateway()
    vecs = await embedder.embed_texts(["a", "b"])
    assert len(vecs) == 2

    store = DummyVectorStore()
    assert await store.hybrid_search(uuid4(), "q", [0.1, 0.2]) == []

    parser = DummyDocumentParser()
    assert parser.supports("text/plain", "note.txt") is True
    assert parser.parse(b"abc", "note.txt") == "abc"

    tool = DummyAgentTool()
    assert await tool.execute(expr="1+1") == "1+1"

    cache = DummyCache()
    cache.set("k", "v", ttl_seconds=60)
    assert cache.get("k") == "v"
    cache.delete("k")
    assert cache.get("k") is None
