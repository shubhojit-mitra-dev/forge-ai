"""Runtime ChatRunnerService for executing published ForgeAI agents."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.exceptions import InvalidToolSelectionError, ValidationDomainError
from app.domain.value_objects.enums import ToolName

if TYPE_CHECKING:
    from app.domain.entities.agent_definition import AgentDefinition, OutputContract
    from app.domain.entities.document import DocumentChunk
    from app.domain.protocols.llm_gateway import EmbeddingGatewayProtocol, LLMGatewayProtocol
    from app.domain.protocols.vector_store import VectorStoreProtocol
    from app.infrastructure.tools.registry import ToolRegistry


class ChatResponse(BaseModel):
    """Immutable response DTO returned by ChatRunnerService."""

    model_config = ConfigDict(frozen=True)

    answer: str
    citations: list[str]
    tools_used: list[ToolName]
    latency_ms: Annotated[int, Field(ge=0)]


def _extract_citations(chunks: list[DocumentChunk]) -> list[str]:
    """Extract unique source filenames in retrieval order."""
    names = [str(chunk.metadata.get("filename", f"chunk-{chunk.chunk_index}")) for chunk in chunks]
    return list(dict.fromkeys(names))


def _enforce_output_contract(
    raw_answer: str,
    contract: OutputContract,
    citations: list[str],
) -> str:
    """Enforce max_response_words and require_citations on the generated answer."""
    answer = raw_answer.strip()
    is_refusal = answer == contract.refusal_template.strip()

    if contract.require_citations and citations and not is_refusal:
        lower_answer = answer.lower()
        has_citation = any(cite.lower() in lower_answer for cite in citations)
        if not has_citation:
            suffix = f"\n\nSources: {', '.join(citations)}"
            suffix_words = len(suffix.split())
            max_body_words = max(1, contract.max_response_words - suffix_words)
            body_words = answer.split()
            if len(body_words) > max_body_words:
                answer = " ".join(body_words[:max_body_words])
            answer = f"{answer}{suffix}"
            return answer

    words = answer.split()
    if len(words) > contract.max_response_words:
        return " ".join(words[: contract.max_response_words])
    return answer


class ChatRunnerService:
    """Executes a published AgentDefinition against RAG, allowed tools, and OutputContract."""

    def __init__(
        self,
        *,
        llm_gateway: LLMGatewayProtocol,
        embedding_gateway: EmbeddingGatewayProtocol,
        vector_store: VectorStoreProtocol,
        tool_registry: ToolRegistry,
        answer_tier: str = "fast-judge",
    ) -> None:
        self._llm = llm_gateway
        self._embeddings = embedding_gateway
        self._vector_store = vector_store
        self._tool_registry = tool_registry
        self._answer_tier = answer_tier

    async def run(
        self,
        *,
        agent_def: AgentDefinition,
        user_message: str,
        history: list[dict[str, str]] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        """Run hybrid RAG, execute allowed tools, invoke LLM, and enforce OutputContract."""
        if not user_message.strip():
            raise ValidationDomainError("EMPTY_MESSAGE", "User message cannot be empty.")

        started = time.monotonic()

        vectors = await self._embeddings.embed_texts([user_message])
        query_embedding = vectors[0] if vectors else []
        chunks = await self._vector_store.hybrid_search(
            project_id=agent_def.project_id,
            query_text=user_message,
            query_embedding=query_embedding,
            top_k=agent_def.retrieval_config.top_k,
            similarity_threshold=agent_def.retrieval_config.similarity_threshold,
        )
        citations = _extract_citations(chunks)

        tools_used, tool_outputs = await self._execute_requested_tools(
            agent_def=agent_def,
            tool_calls=tool_calls or [],
        )

        messages = self._build_messages(
            agent_def=agent_def,
            chunks=chunks,
            tool_outputs=tool_outputs,
            history=history or [],
            user_message=user_message,
        )
        llm_resp = await self._llm.complete(
            messages=messages,
            tier=self._answer_tier,
            temperature=0.0,
            max_tokens=1024,
        )

        enforced_answer = _enforce_output_contract(
            raw_answer=llm_resp.content,
            contract=agent_def.output_contract,
            citations=citations,
        )
        latency_ms = max(0, int((time.monotonic() - started) * 1000))
        return ChatResponse(
            answer=enforced_answer,
            citations=citations,
            tools_used=tools_used,
            latency_ms=latency_ms,
        )

    async def _execute_requested_tools(
        self,
        *,
        agent_def: AgentDefinition,
        tool_calls: list[dict[str, Any]],
    ) -> tuple[list[ToolName], list[str]]:
        allowed = set(agent_def.selected_tools)
        tools_used: list[ToolName] = []
        outputs: list[str] = []

        for call in tool_calls:
            raw_name = str(call.get("name", "")).strip()
            try:
                tool_name = ToolName(raw_name)
            except ValueError as exc:
                raise InvalidToolSelectionError(
                    "UNKNOWN_TOOL",
                    f"Tool '{raw_name}' is not a valid ToolName.",
                ) from exc

            if tool_name not in allowed:
                raise InvalidToolSelectionError(
                    "TOOL_NOT_ALLOWED",
                    f"Tool '{tool_name.value}' is not enabled for agent '{agent_def.slug}'.",
                )

            tool = self._tool_registry.get(tool_name)
            raw_args = call.get("arguments", {})
            args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
            result = await tool.execute(**args)
            tools_used.append(tool_name)
            outputs.append(f"[{tool_name.value}] {result}")

        return tools_used, outputs

    def _build_messages(
        self,
        *,
        agent_def: AgentDefinition,
        chunks: list[DocumentChunk],
        tool_outputs: list[str],
        history: list[dict[str, str]],
        user_message: str,
    ) -> list[dict[str, str]]:
        context_block = "\n\n".join(
            f"[{c.metadata.get('filename', 'source')}] {c.content}" for c in chunks
        )
        sections = [f"Context:\n{context_block or '(No relevant documents retrieved)'}"]
        if tool_outputs:
            sections.append("Tool Results:\n" + "\n".join(tool_outputs))
        sections.append(f"Question: {user_message}")

        messages: list[dict[str, str]] = [{"role": "system", "content": agent_def.system_prompt}]
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": "\n\n".join(sections)})
        return messages
