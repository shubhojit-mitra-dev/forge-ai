"""Unit tests for JudgeService (Stage A deterministic checks + Stage B bias-defended LLM judge)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.services.judge_service import (
    JudgeService,
    normalize_response_for_judge,
    run_deterministic_checks,
    shuffle_chunks_deterministically,
)
from app.domain.entities.agent_definition import OutputContract
from app.domain.entities.document import DocumentChunk
from app.domain.entities.evaluation import EvalCase
from app.domain.exceptions import ValidationDomainError
from app.domain.protocols.llm_gateway import LLMResponse
from app.domain.value_objects.enums import EvalCaseType, FailureCategory


class FakeLLMGateway:
    """Deterministic fake LLMGatewayProtocol for testing JudgeService."""

    def __init__(self, payload: dict[str, Any], model: str = "qwen3-32b") -> None:
        self.payload = payload
        self.model = model
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
            content=json.dumps(self.payload),
            model=self.model,
            prompt_tokens=120,
            completion_tokens=45,
            latency_ms=25,
        )


def _make_chunk(
    idx: int, project_id: UUID, doc_id: UUID, filename: str = "policy.pdf"
) -> DocumentChunk:
    return DocumentChunk(
        id=uuid4(),
        document_id=doc_id,
        project_id=project_id,
        chunk_index=idx,
        content=f"Chunk {idx}: PTO accrual is 15 days per year.",
        content_hash=f"hash-{idx}",
        token_count=12,
        metadata={"filename": filename},
    )


def _make_eval_case(
    *,
    should_refuse: bool = False,
    expected_sources: list[str] | None = None,
    expected_facts: list[str] | None = None,
) -> EvalCase:
    return EvalCase(
        id=uuid4(),
        project_id=uuid4(),
        case_type=EvalCaseType.REFUSAL if should_refuse else EvalCaseType.ANSWERABLE,
        question=(
            "What is the annual PTO allowance?"
            if not should_refuse
            else "What is the CEO's salary?"
        ),
        expected_sources=expected_sources if expected_sources is not None else ["policy.pdf"],
        expected_facts=expected_facts if expected_facts is not None else ["15 days per year"],
        should_refuse=should_refuse,
        rationale="Grounded in HR policy.",
    )


@pytest.mark.unit
def test_deterministic_checks_pass_valid_answerable_response() -> None:
    case = _make_eval_case()
    contract = OutputContract(require_citations=True, max_response_words=100)
    response = "According to policy.pdf, employees receive 15 days per year of PTO."

    checks = run_deterministic_checks(case, response, contract)

    assert checks["refusal_match"] is True
    assert checks["citation_present"] is True
    assert checks["fact_anchors"] is True
    assert checks["within_word_limit"] is True


@pytest.mark.unit
def test_deterministic_checks_detect_missing_citation_and_word_limit() -> None:
    case = _make_eval_case(expected_sources=["handbook.pdf"])
    contract = OutputContract(require_citations=True, max_response_words=50)
    long_response = " ".join(["word"] * 60) + " 15 days per year"

    checks = run_deterministic_checks(case, long_response, contract)

    assert checks["citation_present"] is False
    assert checks["within_word_limit"] is False


@pytest.mark.unit
def test_deterministic_checks_refusal_pattern_matching() -> None:
    case = _make_eval_case(should_refuse=True, expected_sources=[], expected_facts=[])
    contract = OutputContract(require_citations=True, max_response_words=100)

    good_refusal = "I cannot answer this based on the provided documents."
    bad_answer = "The CEO earns $450,000 per year."

    assert run_deterministic_checks(case, good_refusal, contract)["refusal_match"] is True
    assert run_deterministic_checks(case, bad_answer, contract)["refusal_match"] is False


@pytest.mark.unit
def test_shuffle_chunks_is_deterministic_by_eval_case_id() -> None:
    project_id = uuid4()
    doc_id = uuid4()
    chunks = [_make_chunk(i, project_id, doc_id) for i in range(6)]
    case_id = UUID("11111111-2222-3333-4444-555555555555")

    first = shuffle_chunks_deterministically(chunks, case_id)
    second = shuffle_chunks_deterministically(chunks, case_id)

    assert [c.chunk_index for c in first] == [c.chunk_index for c in second]
    assert {c.chunk_index for c in first} == {0, 1, 2, 3, 4, 5}


@pytest.mark.unit
def test_normalize_response_strips_markdown_and_truncates() -> None:
    raw = "## **Summary**\n\n- **PTO**: 15 days per year.\n" + ("extra " * 50)
    normalized = normalize_response_for_judge(raw, max_words=12)

    assert "**" not in normalized
    assert "##" not in normalized
    assert len(normalized.split()) <= 12


@pytest.mark.unit
async def test_judge_service_enforces_cross_model_separation() -> None:
    gateway = FakeLLMGateway(
        payload={
            "grounded": True,
            "correct": True,
            "refusal_accurate": True,
            "failure_category": "none",
            "reasoning": "Aligned.",
        },
        model="gpt-oss-20b",
    )
    service = JudgeService(
        llm_gateway=gateway,
        judge_tier="fast-judge",
        agent_model="gpt-oss-20b",
    )
    case = _make_eval_case()
    contract = OutputContract()

    with pytest.raises(ValidationDomainError, match="CROSS_MODEL_VIOLATION"):
        await service.evaluate_case(
            eval_case=case,
            agent_response="According to policy.pdf, PTO is 15 days per year.",
            retrieved_chunks=[],
            output_contract=contract,
        )


@pytest.mark.unit
async def test_judge_service_rejects_identical_judge_and_agent_tier() -> None:
    gateway = FakeLLMGateway(payload={})
    with pytest.raises(ValidationDomainError, match="CROSS_MODEL_VIOLATION"):
        JudgeService(
            llm_gateway=gateway,
            judge_tier="orchestrator-primary",
            agent_model="orchestrator-primary",
        )


@pytest.mark.unit
async def test_judge_service_returns_structured_judge_score() -> None:
    gateway = FakeLLMGateway(
        payload={
            "grounded": True,
            "correct": True,
            "refusal_accurate": True,
            "failure_category": "none",
            "reasoning": "Response accurately cites policy.pdf and states 15 days per year.",
        },
        model="gemini-2.5-flash-lite",
    )
    service = JudgeService(
        llm_gateway=gateway,
        judge_tier="fast-judge",
        agent_model="gpt-oss-20b",
    )
    case = _make_eval_case()
    chunks = [_make_chunk(0, case.project_id, uuid4())]
    contract = OutputContract(require_citations=True, max_response_words=150)

    score = await service.evaluate_case(
        eval_case=case,
        agent_response="According to policy.pdf, employees receive 15 days per year.",
        retrieved_chunks=chunks,
        output_contract=contract,
        latency_ms=42,
    )

    assert score.eval_case_id == case.id
    assert score.passed is True
    assert score.failure_category == FailureCategory.NONE
    assert score.deterministic_checks["citation_present"] is True
    assert score.latency_ms == 42
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["tier"] == "fast-judge"
