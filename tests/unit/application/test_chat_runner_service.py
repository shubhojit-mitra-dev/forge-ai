"""Unit tests for ChatRunnerService (strict TDD)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.services.chat_runner_service import ChatResponse, ChatRunnerService
from app.domain.entities.agent_definition import AgentDefinition, OutputContract, RetrievalConfig
from app.domain.entities.document import DocumentChunk
from app.domain.exceptions import InvalidToolSelectionError, ValidationDomainError
from app.domain.protocols.llm_gateway import LLMResponse
from app.domain.value_objects.enums import ToolName
from app.infrastructure.tools.registry import ToolRegistry


class FakeEmbeddingGateway:
    """In-memory fake for EmbeddingGatewayProtocol."""

    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = vector or [0.1, 0.2, 0.3]
        self.calls: list[list[str]] = []

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [self.vector for _ in texts]


class FakeVectorStore:
    """In-memory fake for VectorStoreProtocol."""

    def __init__(self, chunks: list[DocumentChunk] | None = None) -> None:
        self.chunks = chunks or []
        self.search_calls: list[dict[str, Any]] = []

    async def upsert_chunks(self, chunks: list[DocumentChunk]) -> None:
        self.chunks.extend(chunks)

    async def hybrid_search(
        self,
        project_id: UUID,
        query_text: str,
        query_embedding: list[float],
        top_k: int = 5,
        similarity_threshold: float = 0.35,
    ) -> list[DocumentChunk]:
        self.search_calls.append(
            {
                "project_id": project_id,
                "query_text": query_text,
                "query_embedding": query_embedding,
                "top_k": top_k,
                "similarity_threshold": similarity_threshold,
            }
        )
        return self.chunks[:top_k]


class FakeLLMGateway:
    """In-memory fake for LLMGatewayProtocol."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[dict[str, str]],
        tier: str = "orchestrator-primary",
        temperature: float = 0.0,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": messages,
                "tier": tier,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": response_format,
            }
        )
        return LLMResponse(
            content=self.content,
            model="fake-fast-judge",
            prompt_tokens=20,
            completion_tokens=10,
            latency_ms=12,
        )


def _make_agent(
    *,
    selected_tools: list[ToolName] | None = None,
    require_citations: bool = True,
    max_response_words: int = 350,
) -> AgentDefinition:
    return AgentDefinition(
        id=uuid4(),
        project_id=uuid4(),
        slug="hr-policy-bot",
        version=1,
        system_prompt=(
            "You are a helpful HR policy assistant grounded strictly in company documents."
        ),
        retrieval_config=RetrievalConfig(top_k=4, similarity_threshold=0.4),
        selected_tools=selected_tools or [],
        output_contract=OutputContract(
            format="markdown",
            require_citations=require_citations,
            refusal_template="I cannot answer this based on the provided documents.",
            max_response_words=max_response_words,
        ),
        is_published=True,
    )


def _make_chunk(project_id: UUID, filename: str, content: str) -> DocumentChunk:
    return DocumentChunk(
        id=uuid4(),
        document_id=uuid4(),
        project_id=project_id,
        chunk_index=0,
        content=content,
        content_hash="abc123",
        token_count=10,
        metadata={"filename": filename},
        similarity=0.88,
    )


@pytest.mark.unit
async def test_chat_runner_retrieves_chunks_and_appends_citations() -> None:
    agent = _make_agent(require_citations=True)
    chunk = _make_chunk(agent.project_id, "handbook.md", "Employees get 20 days of PTO.")
    embeddings = FakeEmbeddingGateway()
    vector_store = FakeVectorStore(chunks=[chunk])
    llm = FakeLLMGateway(content="Full-time employees receive 20 days of PTO annually.")
    service = ChatRunnerService(
        llm_gateway=llm,
        embedding_gateway=embeddings,
        vector_store=vector_store,
        tool_registry=ToolRegistry(),
    )

    result = await service.run(agent_def=agent, user_message="How many PTO days do I get?")

    assert isinstance(result, ChatResponse)
    assert "20 days of PTO" in result.answer
    assert "handbook.md" in result.answer
    assert result.citations == ["handbook.md"]
    assert result.tools_used == []
    assert result.latency_ms >= 0
    assert vector_store.search_calls[0]["top_k"] == 4
    assert vector_store.search_calls[0]["similarity_threshold"] == 0.4
    assert llm.calls[0]["tier"] == "fast-judge"


@pytest.mark.unit
async def test_chat_runner_enforces_max_response_words() -> None:
    agent = _make_agent(require_citations=False, max_response_words=50)
    long_text = " ".join(["policy"] * 80)
    service = ChatRunnerService(
        llm_gateway=FakeLLMGateway(content=long_text),
        embedding_gateway=FakeEmbeddingGateway(),
        vector_store=FakeVectorStore(),
        tool_registry=ToolRegistry(),
    )

    result = await service.run(agent_def=agent, user_message="Summarize policy")

    assert len(result.answer.split()) <= 50


@pytest.mark.unit
async def test_chat_runner_executes_only_selected_tools() -> None:
    agent = _make_agent(selected_tools=[ToolName.CALCULATOR], require_citations=False)
    llm = FakeLLMGateway(content="The total allowance is 42.")
    service = ChatRunnerService(
        llm_gateway=llm,
        embedding_gateway=FakeEmbeddingGateway(),
        vector_store=FakeVectorStore(),
        tool_registry=ToolRegistry(),
    )

    result = await service.run(
        agent_def=agent,
        user_message="Calculate 40 + 2",
        tool_calls=[{"name": "calculator", "arguments": {"expression": "40 + 2"}}],
    )

    assert result.tools_used == [ToolName.CALCULATOR]
    assert "42" in llm.calls[0]["messages"][-1]["content"]


@pytest.mark.unit
async def test_chat_runner_rejects_unselected_tool() -> None:
    agent = _make_agent(selected_tools=[ToolName.CURRENT_DATE], require_citations=False)
    service = ChatRunnerService(
        llm_gateway=FakeLLMGateway(content="Should not reach"),
        embedding_gateway=FakeEmbeddingGateway(),
        vector_store=FakeVectorStore(),
        tool_registry=ToolRegistry(),
    )

    with pytest.raises(InvalidToolSelectionError):
        await service.run(
            agent_def=agent,
            user_message="What is the weather?",
            tool_calls=[{"name": "weather_http", "arguments": {"city": "London"}}],
        )


@pytest.mark.unit
async def test_chat_runner_rejects_empty_user_message() -> None:
    agent = _make_agent()
    service = ChatRunnerService(
        llm_gateway=FakeLLMGateway(content="unused"),
        embedding_gateway=FakeEmbeddingGateway(),
        vector_store=FakeVectorStore(),
        tool_registry=ToolRegistry(),
    )

    with pytest.raises(ValidationDomainError):
        await service.run(agent_def=agent, user_message="   ")
