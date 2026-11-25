"""Unit tests for EvalGeneratorService."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.services.eval_generator import EvalGeneratorService
from app.domain.entities.document import DocumentChunk
from app.domain.entities.evaluation import EvalCase
from app.domain.entities.requirements import ClarifyingQA, RequirementsDoc
from app.domain.exceptions import ValidationDomainError
from app.domain.protocols.llm_gateway import LLMResponse
from app.domain.value_objects.enums import EvalCaseType, ToolName


class FakeLLMGateway:
    """Deterministic fake LLMGatewayProtocol for eval generation tests."""

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
        content = self._responses.pop(0) if self._responses else '{"cases": []}'
        return LLMResponse(
            content=content,
            model="fake-model",
            prompt_tokens=120,
            completion_tokens=400,
            latency_ms=15,
        )


def _sample_requirements() -> RequirementsDoc:
    return RequirementsDoc(
        agent_name="Acme HR Policy Assistant",
        scope="Answer employee questions about PTO, parental leave, and benefits.",
        target_audience="Full-time employees",
        tone="Professional and concise",
        must_answer_topics=["PTO policy", "Parental leave"],
        must_refuse_topics=["Executive compensation", "Medical advice"],
        clarifying_qa=[ClarifyingQA(question="Region?", answer="US only.")],
        detected_tool_needs=[ToolName.CURRENT_DATE],
    )


def _make_chunks(project_id: UUID, count: int = 12) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    for idx in range(count):
        filename = "hr_handbook.md" if idx % 2 == 0 else "benefits_2026.pdf"
        chunks.append(
            DocumentChunk(
                id=uuid4(),
                document_id=uuid4(),
                project_id=project_id,
                chunk_index=idx,
                content=f"Policy section {idx}: Employees accrue 15 days of PTO per year.",
                content_hash=f"hash-{idx}",
                token_count=12,
                metadata={"filename": filename},
            )
        )
    return chunks


def _build_raw_case(
    idx: int,
    case_type: str,
    sources: list[str] | None = None,
    should_refuse: bool | None = None,
) -> dict[str, Any]:
    refuse = case_type == "refusal" if should_refuse is None else should_refuse
    return {
        "case_type": case_type,
        "question": f"Sample {case_type} question #{idx}?",
        "expected_sources": sources
        if sources is not None
        else ([] if refuse else ["hr_handbook.md"]),
        "expected_facts": [] if refuse else [f"Fact {idx} from policy"],
        "should_refuse": refuse,
        "rationale": f"Tests {case_type} behavior #{idx}.",
    }


@pytest.mark.unit
async def test_eval_generator_produces_at_least_20_cases_across_all_types() -> None:
    """EvalGeneratorService batches chunks and generates >= 20 cases across all 3 types."""
    project_id = uuid4()
    chunks = _make_chunks(project_id, count=12)

    batch_1 = {
        "cases": [
            *[_build_raw_case(i, "answerable") for i in range(1, 7)],
            *[_build_raw_case(i, "refusal") for i in range(1, 4)],
            *[
                _build_raw_case(i, "edge", ["hr_handbook.md", "benefits_2026.pdf"])
                for i in range(1, 3)
            ],
        ]
    }
    batch_2 = {
        "cases": [
            *[_build_raw_case(i, "answerable") for i in range(7, 12)],
            *[_build_raw_case(i, "refusal") for i in range(4, 7)],
            *[
                _build_raw_case(i, "edge", ["hr_handbook.md", "benefits_2026.pdf"])
                for i in range(3, 6)
            ],
        ]
    }
    llm = FakeLLMGateway([json.dumps(batch_1), json.dumps(batch_2)])
    service = EvalGeneratorService(llm_gateway=llm)

    cases = await service.generate(
        project_id=project_id,
        requirements=_sample_requirements(),
        chunks=chunks,
    )

    assert len(llm.calls) == 2
    assert len(cases) >= 20
    assert all(isinstance(c, EvalCase) for c in cases)

    answerable = [c for c in cases if c.case_type == EvalCaseType.ANSWERABLE]
    refusal = [c for c in cases if c.case_type == EvalCaseType.REFUSAL]
    edge = [c for c in cases if c.case_type == EvalCaseType.EDGE]

    assert len(answerable) >= 10
    assert len(refusal) >= 5
    assert len(edge) >= 4

    for case in cases:
        assert case.question.strip()
        assert isinstance(case.should_refuse, bool)
        if case.case_type == EvalCaseType.REFUSAL:
            assert case.should_refuse is True
        else:
            assert case.should_refuse is False
            assert len(case.expected_sources) >= 1


@pytest.mark.unit
async def test_eval_generator_tops_up_when_initial_batches_under_20() -> None:
    """EvalGeneratorService runs a top-up call if initial chunk batches yield < 20 cases."""
    project_id = uuid4()
    chunks = _make_chunks(project_id, count=4)

    initial_batch = {
        "cases": [
            *[_build_raw_case(i, "answerable") for i in range(1, 7)],
            *[_build_raw_case(i, "refusal") for i in range(1, 4)],
            *[_build_raw_case(i, "edge") for i in range(1, 3)],
        ]
    }
    topup_batch = {
        "cases": [
            *[_build_raw_case(i, "answerable") for i in range(7, 13)],
            *[_build_raw_case(i, "refusal") for i in range(4, 7)],
            *[_build_raw_case(i, "edge") for i in range(3, 6)],
        ]
    }
    llm = FakeLLMGateway([json.dumps(initial_batch), json.dumps(topup_batch)])
    service = EvalGeneratorService(llm_gateway=llm)

    cases = await service.generate(
        project_id=project_id,
        requirements=_sample_requirements(),
        chunks=chunks,
    )

    assert len(cases) >= 20
    assert len(llm.calls) == 2


@pytest.mark.unit
async def test_eval_generator_raises_when_chunks_empty() -> None:
    """EvalGeneratorService raises ValidationDomainError when no chunks are provided."""
    llm = FakeLLMGateway([])
    service = EvalGeneratorService(llm_gateway=llm)

    with pytest.raises(ValidationDomainError, match="NO_CHUNKS_FOR_EVAL"):
        await service.generate(
            project_id=uuid4(),
            requirements=_sample_requirements(),
            chunks=[],
        )


@pytest.mark.unit
async def test_eval_generator_filters_invalid_cases_and_raises_if_below_minimum() -> None:
    """Invalid cases (empty question or missing expected_sources) are rejected."""
    project_id = uuid4()
    chunks = _make_chunks(project_id, count=4)

    bad_payload = {
        "cases": [
            _build_raw_case(1, "answerable", sources=[]),  # invalid: no expected_sources
            {
                "case_type": "answerable",
                "question": "   ",
                "expected_sources": ["a.md"],
                "should_refuse": False,
            },
            _build_raw_case(2, "answerable", sources=["hr_handbook.md"]),
        ]
    }
    llm = FakeLLMGateway([json.dumps(bad_payload)] * 4)
    service = EvalGeneratorService(llm_gateway=llm)

    with pytest.raises(ValidationDomainError, match="INSUFFICIENT_EVAL_CASES"):
        await service.generate(
            project_id=project_id,
            requirements=_sample_requirements(),
            chunks=chunks,
        )
