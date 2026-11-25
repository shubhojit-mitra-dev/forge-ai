"""Stage 3: AgentGeneratorService with strict tool discipline."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID, uuid4

from app.application.prompts.generator_prompts import build_agent_generator_messages
from app.domain.entities.agent_definition import (
    AgentDefinition,
    OutputContract,
    RetrievalConfig,
)
from app.domain.exceptions import ValidationDomainError
from app.domain.value_objects.enums import ToolName
from app.infrastructure.tools.registry import ToolRegistry, get_tool_registry

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.entities.requirements import RequirementsDoc
    from app.domain.protocols.llm_gateway import LLMGatewayProtocol

_WEATHER_KEYWORDS: tuple[str, ...] = (
    "weather",
    "forecast",
    "temperature",
    "meteorolog",
    "climate",
    "rainfall",
    "humidity",
    "wind speed",
    "storm",
)

_CSV_KEYWORDS: tuple[str, ...] = (
    ".csv",
    "csv",
    "table",
    "tabular",
    "spreadsheet",
    "catalog",
    "inventory",
    "spares",
    "spare parts",
    "part number",
    "sku",
    "pricing",
    "unit price",
    "stock",
    "lookup",
    "dataset",
    "ledger",
)


def _extract_json_object(raw_content: str) -> dict[str, Any]:
    """Parse a JSON object from LLM output, stripping optional markdown fences."""
    cleaned = raw_content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValidationDomainError(
            code="AGENT_GENERATION_INVALID",
            detail=f"LLM returned malformed JSON for AgentDefinition: {exc}",
        ) from exc
    if not isinstance(parsed, dict):
        raise ValidationDomainError(
            code="AGENT_GENERATION_INVALID",
            detail="AgentDefinition LLM output must be a JSON object.",
        )
    return parsed


def _slugify(agent_name: str) -> str:
    """Convert an agent name into a URL-safe lowercase slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", agent_name.lower()).strip("-")
    return slug or "forge-agent"


def _is_tool_justified_for_brief(
    tool: ToolName,
    requirements: RequirementsDoc,
    doc_summaries: Sequence[str],
) -> bool:
    """Enforce domain compatibility rules so irrelevant tools are never attached."""
    corpus = " ".join(
        [
            requirements.agent_name,
            requirements.scope,
            *requirements.must_answer_topics,
            *doc_summaries,
        ]
    ).lower()

    if tool == ToolName.WEATHER_HTTP:
        return any(kw in corpus for kw in _WEATHER_KEYWORDS)
    if tool == ToolName.CSV_LOOKUP:
        return any(kw in corpus for kw in _CSV_KEYWORDS)
    return True


class AgentGeneratorService:
    """Generates a validated AgentDefinition from RequirementsDoc and document summaries."""

    def __init__(
        self,
        llm_gateway: LLMGatewayProtocol,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._llm = llm_gateway
        self._tool_registry = tool_registry if tool_registry is not None else get_tool_registry()

    async def generate(
        self,
        project_id: UUID,
        requirements: RequirementsDoc,
        doc_summaries: Sequence[str],
        *,
        version: int = 1,
        agent_id: UUID | None = None,
        slug: str | None = None,
    ) -> AgentDefinition:
        """Generate an AgentDefinition with strict tool selection discipline."""
        tool_descriptions = [
            (tool.name.value, tool.description) for tool in self._tool_registry.list_tools()
        ]
        messages = build_agent_generator_messages(
            requirements=requirements,
            doc_summaries=doc_summaries,
            tool_descriptions=tool_descriptions,
        )
        response = await self._llm.complete(
            messages=messages,
            tier="orchestrator-primary",
            temperature=0.1,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        payload = _extract_json_object(response.content)

        system_prompt = payload.get("system_prompt")
        if not isinstance(system_prompt, str) or len(system_prompt.strip()) < 50:
            raise ValidationDomainError(
                code="AGENT_GENERATION_INVALID",
                detail="Generated system_prompt must be a string of at least 50 characters.",
            )

        retrieval_config = self._build_retrieval_config(payload.get("retrieval_config"))
        output_contract = self._build_output_contract(payload.get("output_contract"))
        selected_tools = self._select_disciplined_tools(
            raw_selected=payload.get("selected_tools", []),
            requirements=requirements,
            doc_summaries=doc_summaries,
        )

        return AgentDefinition(
            id=agent_id if agent_id is not None else uuid4(),
            project_id=project_id,
            slug=slug if slug is not None else _slugify(requirements.agent_name),
            version=version,
            system_prompt=system_prompt.strip(),
            retrieval_config=retrieval_config,
            selected_tools=selected_tools,
            output_contract=output_contract,
        )

    def _select_disciplined_tools(
        self,
        raw_selected: Any,
        requirements: RequirementsDoc,
        doc_summaries: Sequence[str],
    ) -> list[ToolName]:
        """Validate selected tools against detected_tool_needs and domain rules."""
        available = set(self._tool_registry.available_names())
        allowed_tools: list[ToolName] = [
            tool
            for tool in dict.fromkeys(requirements.detected_tool_needs)
            if tool in available and _is_tool_justified_for_brief(tool, requirements, doc_summaries)
        ]
        allowed_set = set(allowed_tools)

        validated: list[ToolName] = []
        if isinstance(raw_selected, list):
            for item in raw_selected:
                if not isinstance(item, str):
                    continue
                try:
                    tool_enum = ToolName(item)
                except ValueError:
                    continue
                if tool_enum in allowed_set and tool_enum not in validated:
                    validated.append(tool_enum)

        for required_tool in allowed_tools:
            if required_tool not in validated:
                validated.append(required_tool)

        return validated

    @staticmethod
    def _build_retrieval_config(raw: Any) -> RetrievalConfig:
        if raw is None:
            return RetrievalConfig()
        if not isinstance(raw, dict):
            raise ValidationDomainError(
                code="AGENT_GENERATION_INVALID",
                detail="retrieval_config must be an object.",
            )
        try:
            return RetrievalConfig(
                chunk_size=int(raw.get("chunk_size", 600)),
                chunk_overlap=int(raw.get("chunk_overlap", 100)),
                top_k=int(raw.get("top_k", 5)),
                similarity_threshold=float(raw.get("similarity_threshold", 0.35)),
                hybrid_search=bool(raw.get("hybrid_search", True)),
            )
        except (TypeError, ValueError) as exc:
            raise ValidationDomainError(
                code="AGENT_GENERATION_INVALID",
                detail=f"Invalid retrieval_config: {exc}",
            ) from exc

    @staticmethod
    def _build_output_contract(raw: Any) -> OutputContract:
        if raw is None:
            return OutputContract()
        if not isinstance(raw, dict):
            raise ValidationDomainError(
                code="AGENT_GENERATION_INVALID",
                detail="output_contract must be an object.",
            )
        raw_format = raw.get("format", "markdown")
        if raw_format not in ("markdown", "json"):
            raise ValidationDomainError(
                code="AGENT_GENERATION_INVALID",
                detail=f"Unsupported output_contract format: {raw_format!r}",
            )
        fmt = cast("Literal['markdown', 'json']", raw_format)
        refusal_template = str(
            raw.get("refusal_template", "I cannot answer this based on the provided documents.")
        ).strip()
        if not refusal_template:
            refusal_template = "I cannot answer this based on the provided documents."
        try:
            return OutputContract(
                format=fmt,
                require_citations=bool(raw.get("require_citations", True)),
                refusal_template=refusal_template,
                max_response_words=int(raw.get("max_response_words", 350)),
            )
        except (TypeError, ValueError) as exc:
            raise ValidationDomainError(
                code="AGENT_GENERATION_INVALID",
                detail=f"Invalid output_contract: {exc}",
            ) from exc
