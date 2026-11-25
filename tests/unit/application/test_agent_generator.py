"""Unit tests for AgentGeneratorService and strict tool discipline."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest

from app.application.services.agent_generator import AgentGeneratorService
from app.domain.entities.agent_definition import AgentDefinition
from app.domain.entities.requirements import ClarifyingQA, RequirementsDoc
from app.domain.exceptions import ValidationDomainError
from app.domain.protocols.llm_gateway import LLMResponse
from app.domain.value_objects.enums import ToolName
from app.infrastructure.tools.registry import ToolRegistry


class FakeLLMGateway:
    """Deterministic fake LLMGatewayProtocol for unit tests."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
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
        content = self._responses.pop(0) if self._responses else "{}"
        return LLMResponse(
            content=content,
            model="fake-model",
            prompt_tokens=100,
            completion_tokens=150,
            latency_ms=10,
        )


def _hr_requirements(
    detected_tool_needs: list[ToolName] | None = None,
) -> RequirementsDoc:
    return RequirementsDoc(
        agent_name="Acme HR Policy Assistant",
        scope="Answer employee questions about PTO, parental leave, and benefits policies.",
        target_audience="Full-time corporate employees",
        tone="Professional, empathetic, and concise",
        must_answer_topics=[
            "Annual PTO accrual and carryover",
            "Parental leave eligibility",
        ],
        must_refuse_topics=[
            "Individual employee salary data",
            "Legal advice or medical diagnoses",
        ],
        clarifying_qa=[
            ClarifyingQA(
                question="Should US and EU policies be separated?",
                answer="Focus on US handbook only.",
            )
        ],
        detected_tool_needs=(
            detected_tool_needs if detected_tool_needs is not None else [ToolName.CURRENT_DATE]
        ),
    )


def _ship_spares_requirements(
    detected_tool_needs: list[ToolName] | None = None,
) -> RequirementsDoc:
    return RequirementsDoc(
        agent_name="Maritime Ship Spares Advisor",
        scope=(
            "Look up vessel spare parts inventory, unit pricing from CSV catalogs, "
            "and calculate total order quantities and costs."
        ),
        target_audience="Marine procurement engineers",
        tone="Technical and precise",
        must_answer_topics=[
            "Part number stock levels and unit prices",
            "Order subtotal and tax calculations",
        ],
        must_refuse_topics=[
            "Unverified third-party supplier warranties",
        ],
        clarifying_qa=[
            ClarifyingQA(
                question="Which currency is used?",
                answer="USD only.",
            )
        ],
        detected_tool_needs=(
            detected_tool_needs
            if detected_tool_needs is not None
            else [ToolName.CSV_LOOKUP, ToolName.CALCULATOR]
        ),
    )


@pytest.mark.unit
async def test_hr_brief_excludes_weather_http_and_csv_lookup() -> None:
    """HR brief must never attach weather_http or csv_lookup even if LLM suggests them."""
    llm_payload = {
        "system_prompt": (
            "You are the Acme HR Policy Assistant. Answer employee questions strictly from "
            "the provided HR handbook documents, cite sources, and refuse out-of-scope requests."
        ),
        "retrieval_config": {
            "chunk_size": 600,
            "chunk_overlap": 100,
            "top_k": 5,
            "similarity_threshold": 0.35,
            "hybrid_search": True,
        },
        "selected_tools": ["weather_http", "csv_lookup", "current_date"],
        "output_contract": {
            "format": "markdown",
            "require_citations": True,
            "refusal_template": "I cannot answer this based on the provided HR documents.",
            "max_response_words": 300,
        },
    }
    llm = FakeLLMGateway([json.dumps(llm_payload)])
    service = AgentGeneratorService(llm_gateway=llm, tool_registry=ToolRegistry())

    agent = await service.generate(
        project_id=uuid4(),
        requirements=_hr_requirements(detected_tool_needs=[ToolName.CURRENT_DATE]),
        doc_summaries=["hr_handbook_2026.pdf: Covers PTO, parental leave, and 401k benefits."],
    )

    assert isinstance(agent, AgentDefinition)
    assert ToolName.WEATHER_HTTP not in agent.selected_tools
    assert ToolName.CSV_LOOKUP not in agent.selected_tools
    assert ToolName.CURRENT_DATE in agent.selected_tools
    assert agent.version == 1
    assert agent.slug == "acme-hr-policy-assistant"
    assert len(agent.system_prompt) >= 50
    assert len(llm.calls) == 1


@pytest.mark.unit
async def test_hr_brief_blocks_weather_http_even_if_in_detected_tool_needs() -> None:
    """Domain rules block weather_http on HR/procurement briefs even if intake flagged it."""
    llm_payload = {
        "system_prompt": (
            "You are the Acme HR Policy Assistant. Answer employee questions strictly from "
            "the provided HR handbook documents and refuse out-of-scope topics."
        ),
        "selected_tools": ["weather_http"],
    }
    llm = FakeLLMGateway([json.dumps(llm_payload)])
    service = AgentGeneratorService(llm_gateway=llm, tool_registry=ToolRegistry())

    agent = await service.generate(
        project_id=uuid4(),
        requirements=_hr_requirements(detected_tool_needs=[ToolName.WEATHER_HTTP]),
        doc_summaries=["hr_handbook_2026.pdf: Employee leave and benefits policy."],
    )

    assert ToolName.WEATHER_HTTP not in agent.selected_tools
    assert agent.selected_tools == []


@pytest.mark.unit
async def test_ship_spares_brief_includes_csv_lookup_and_calculator_excludes_weather() -> None:
    """Ship-spares brief must include csv_lookup and calculator, and exclude weather_http."""
    llm_payload = {
        "system_prompt": (
            "You are the Maritime Ship Spares Advisor. Use the CSV parts catalog and calculator "
            "to provide exact part availability, pricing, and order totals with citations."
        ),
        "retrieval_config": {
            "chunk_size": 500,
            "chunk_overlap": 80,
            "top_k": 6,
            "similarity_threshold": 0.30,
            "hybrid_search": True,
        },
        "selected_tools": ["csv_lookup", "weather_http"],
        "output_contract": {
            "format": "markdown",
            "require_citations": True,
            "refusal_template": "This spare part or request is outside the provided catalog.",
            "max_response_words": 350,
        },
    }
    llm = FakeLLMGateway([json.dumps(llm_payload)])
    service = AgentGeneratorService(llm_gateway=llm, tool_registry=ToolRegistry())

    agent = await service.generate(
        project_id=uuid4(),
        requirements=_ship_spares_requirements(),
        doc_summaries=[
            "ship_spares_inventory.csv: Part numbers, stock counts, and USD unit prices.",
            "procurement_rules.md: Bulk order discounts and shipping terms.",
        ],
    )

    assert ToolName.CSV_LOOKUP in agent.selected_tools
    assert ToolName.CALCULATOR in agent.selected_tools
    assert ToolName.WEATHER_HTTP not in agent.selected_tools


@pytest.mark.unit
async def test_agent_generator_strips_unknown_tool_names() -> None:
    """Unknown tool names hallucinated by the LLM are stripped cleanly."""
    llm_payload = {
        "system_prompt": (
            "You are a precise Maritime Ship Spares Advisor. Always cite part numbers "
            "and compute totals accurately."
        ),
        "selected_tools": ["sql_executor", "calculator", "csv_lookup"],
    }
    llm = FakeLLMGateway([json.dumps(llm_payload)])
    service = AgentGeneratorService(llm_gateway=llm, tool_registry=ToolRegistry())

    agent = await service.generate(
        project_id=uuid4(),
        requirements=_ship_spares_requirements(),
        doc_summaries=["spares.csv: Marine spare parts catalog."],
    )

    assert set(agent.selected_tools) == {ToolName.CSV_LOOKUP, ToolName.CALCULATOR}


@pytest.mark.unit
async def test_agent_generator_raises_on_malformed_llm_json() -> None:
    """Malformed LLM response raises ValidationDomainError."""
    llm = FakeLLMGateway(["not valid json at all"])
    service = AgentGeneratorService(llm_gateway=llm, tool_registry=ToolRegistry())

    with pytest.raises(ValidationDomainError, match="AGENT_GENERATION_INVALID"):
        await service.generate(
            project_id=uuid4(),
            requirements=_hr_requirements(),
            doc_summaries=["hr.pdf: HR policy."],
        )
