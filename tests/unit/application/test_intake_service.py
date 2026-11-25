"""Unit tests for IntakeService (Stage 1: clarifying questions & RequirementsDoc)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.application.services.intake_service import IntakeService
from app.domain.entities.requirements import ClarifyingQA, RequirementsDoc
from app.domain.exceptions import ValidationDomainError
from app.domain.protocols.llm_gateway import LLMResponse
from app.domain.value_objects.enums import ToolName


def _make_llm_response(payload: dict[str, object]) -> LLMResponse:
    return LLMResponse(
        content=json.dumps(payload),
        model="mock-model",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=12,
    )


@pytest.mark.unit
async def test_generate_questions_caps_at_five() -> None:
    llm_gateway = AsyncMock()
    llm_gateway.complete.return_value = _make_llm_response(
        {
            "questions": [
                "Question 1?",
                "Question 2?",
                "Question 3?",
                "Question 4?",
                "Question 5?",
                "Question 6?",
                "Question 7?",
                "Question 8?",
            ]
        }
    )

    service = IntakeService(llm_gateway=llm_gateway)
    questions = await service.generate_questions(
        brief="Build an HR policy assistant for employees.",
        doc_summaries=["handbook.pdf: PTO, benefits, and leave policies."],
    )

    assert len(questions) == 5
    assert questions == [
        "Question 1?",
        "Question 2?",
        "Question 3?",
        "Question 4?",
        "Question 5?",
    ]
    llm_gateway.complete.assert_awaited_once()


@pytest.mark.unit
async def test_generate_questions_empty_brief_raises_validation_error() -> None:
    service = IntakeService(llm_gateway=AsyncMock())

    with pytest.raises(ValidationDomainError) as exc_info:
        await service.generate_questions(brief="   ", doc_summaries=[])

    assert exc_info.value.code == "EMPTY_BRIEF"


@pytest.mark.unit
async def test_finalize_requirements_produces_requirements_doc() -> None:
    llm_gateway = AsyncMock()
    llm_gateway.complete.return_value = _make_llm_response(
        {
            "agent_name": "Ship Spares Inventory Assistant",
            "scope": "Answer spare part availability and pricing from catalog CSV.",
            "target_audience": "Marine engineers and procurement officers",
            "tone": "Concise and technical",
            "must_answer_topics": ["Part stock levels", "Unit pricing calculations"],
            "must_refuse_topics": ["Weather forecasts", "HR payroll"],
            "detected_tool_needs": ["csv_lookup", "calculator"],
        }
    )

    qa_pairs = [
        ClarifyingQA(
            question="Should it calculate bulk order totals?",
            answer="Yes, compute total cost for requested quantities.",
        )
    ]

    service = IntakeService(llm_gateway=llm_gateway)
    req = await service.finalize_requirements(
        brief="Build a ship spares assistant using the parts CSV.",
        doc_summaries=["spares.csv: part_id, name, qty, unit_price_usd"],
        qa_pairs=qa_pairs,
    )

    assert isinstance(req, RequirementsDoc)
    assert req.agent_name == "Ship Spares Inventory Assistant"
    assert req.must_answer_topics == ["Part stock levels", "Unit pricing calculations"]
    assert req.must_refuse_topics == ["Weather forecasts", "HR payroll"]
    assert req.clarifying_qa == qa_pairs
    assert req.detected_tool_needs == [ToolName.CSV_LOOKUP, ToolName.CALCULATOR]


@pytest.mark.unit
async def test_finalize_requirements_rejects_more_than_five_qa_pairs() -> None:
    service = IntakeService(llm_gateway=AsyncMock())
    too_many_qas = [ClarifyingQA(question=f"Q{i}", answer=f"A{i}") for i in range(6)]

    with pytest.raises(ValidationDomainError) as exc_info:
        await service.finalize_requirements(
            brief="Build an HR policy assistant.",
            doc_summaries=["handbook.pdf"],
            qa_pairs=too_many_qas,
        )

    assert exc_info.value.code == "TOO_MANY_CLARIFYING_QUESTIONS"


@pytest.mark.unit
async def test_finalize_requirements_invalid_json_raises_validation_error() -> None:
    llm_gateway = AsyncMock()
    llm_gateway.complete.return_value = LLMResponse(
        content="not valid json at all",
        model="mock-model",
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms=5,
    )

    service = IntakeService(llm_gateway=llm_gateway)

    with pytest.raises(ValidationDomainError) as exc_info:
        await service.finalize_requirements(
            brief="Build an HR policy assistant.",
            doc_summaries=["handbook.pdf"],
            qa_pairs=[],
        )

    assert exc_info.value.code == "INVALID_LLM_JSON"
