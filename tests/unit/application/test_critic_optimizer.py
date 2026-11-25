"""Unit tests for CriticOptimizerService (failure classification & targeted patching)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.services.critic_optimizer import CriticOptimizerService
from app.domain.entities.agent_definition import (
    AgentDefinition,
    OutputContract,
    RetrievalConfig,
)
from app.domain.entities.evaluation import EvalCase, JudgeScore
from app.domain.protocols.llm_gateway import LLMResponse
from app.domain.value_objects.enums import EvalCaseType, FailureCategory, ToolName


class FakePatchLLMGateway:
    """Fake LLMGatewayProtocol returning surgical patch JSON."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[dict[str, str]],
        tier: str = "orchestrator-primary",
        temperature: float = 0.0,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "tier": tier})
        return LLMResponse(
            content=json.dumps(
                {
                    "what_changed": "Added explicit citation and grounding guardrail.",
                    "why": "Address prompt_defect and hallucination failures.",
                    "patched_system_prompt": (
                        "You are an HR policy assistant. Always cite filenames and only state "
                        "facts directly supported by retrieved context."
                    ),
                    "patched_refusal_template": None,
                    "patched_require_citations": True,
                    "patched_max_response_words": None,
                }
            ),
            model="gemini-2.5-flash",
            prompt_tokens=150,
            completion_tokens=60,
            latency_ms=30,
        )


def _make_agent() -> AgentDefinition:
    return AgentDefinition(
        id=uuid4(),
        project_id=uuid4(),
        slug="hr-policy-bot",
        version=1,
        system_prompt=(
            "You are an HR policy assistant. Answer employee questions clearly and concisely."
        ),
        retrieval_config=RetrievalConfig(
            chunk_size=600,
            chunk_overlap=100,
            top_k=5,
            similarity_threshold=0.35,
            hybrid_search=True,
        ),
        selected_tools=[ToolName.CURRENT_DATE],
        output_contract=OutputContract(require_citations=True, max_response_words=350),
    )


def _make_scores(
    categories: list[FailureCategory],
    project_id: UUID,
) -> tuple[list[EvalCase], list[JudgeScore]]:
    cases: list[EvalCase] = []
    scores: list[JudgeScore] = []
    for i, cat in enumerate(categories):
        case = EvalCase(
            id=uuid4(),
            project_id=project_id,
            case_type=EvalCaseType.ANSWERABLE,
            question=f"Question {i}?",
            expected_sources=["policy.pdf"],
            expected_facts=["fact"],
            should_refuse=False,
            rationale="Test case",
        )
        passed = cat == FailureCategory.NONE
        scores.append(
            JudgeScore(
                eval_case_id=case.id,
                grounded=passed,
                correct=passed,
                refusal_accurate=passed,
                passed=passed,
                failure_category=cat,
                reasoning="ok" if passed else f"failed due to {cat.value}",
            )
        )
        cases.append(case)
    return cases, scores


@pytest.mark.unit
async def test_retrieval_miss_updates_only_retrieval_config() -> None:
    gateway = FakePatchLLMGateway()
    optimizer = CriticOptimizerService(llm_gateway=gateway)
    agent = _make_agent()
    _, initial_scores = _make_scores(
        [
            FailureCategory.RETRIEVAL_MISS,
            FailureCategory.RETRIEVAL_MISS,
            FailureCategory.NONE,
        ],
        agent.project_id,
    )
    _, improved_scores = _make_scores(
        [FailureCategory.NONE, FailureCategory.NONE, FailureCategory.NONE],
        agent.project_id,
    )

    call_count = 0

    async def evaluate_fn(candidate: AgentDefinition) -> list[JudgeScore]:
        nonlocal call_count
        call_count += 1
        return initial_scores if call_count == 1 else improved_scores

    result = await optimizer.optimize(agent=agent, evaluate_fn=evaluate_fn)

    assert len(result.iteration_logs) == 1
    log = result.iteration_logs[0]
    assert log.change_type == "retrieval_config"
    assert result.final_agent.version == 2
    assert result.final_agent.retrieval_config.top_k > agent.retrieval_config.top_k
    assert (
        result.final_agent.retrieval_config.similarity_threshold
        < agent.retrieval_config.similarity_threshold
    )
    # Targeted patch: system_prompt and selected_tools must remain untouched
    assert result.final_agent.system_prompt == agent.system_prompt
    assert result.final_agent.selected_tools == agent.selected_tools
    assert len(gateway.calls) == 0  # retrieval_config patch is deterministic


@pytest.mark.unit
@pytest.mark.parametrize(
    "dominant_category",
    [
        FailureCategory.PROMPT_DEFECT,
        FailureCategory.HALLUCINATION,
        FailureCategory.WRONG_REFUSAL,
    ],
)
async def test_prompt_and_refusal_defects_apply_surgical_prompt_patch(
    dominant_category: FailureCategory,
) -> None:
    gateway = FakePatchLLMGateway()
    optimizer = CriticOptimizerService(llm_gateway=gateway)
    agent = _make_agent()
    _, failing_scores = _make_scores(
        [dominant_category, dominant_category, FailureCategory.NONE],
        agent.project_id,
    )
    _, passing_scores = _make_scores(
        [FailureCategory.NONE, FailureCategory.NONE, FailureCategory.NONE],
        agent.project_id,
    )

    call_count = 0

    async def evaluate_fn(candidate: AgentDefinition) -> list[JudgeScore]:
        nonlocal call_count
        call_count += 1
        return failing_scores if call_count == 1 else passing_scores

    result = await optimizer.optimize(agent=agent, evaluate_fn=evaluate_fn)

    assert len(result.iteration_logs) == 1
    assert result.iteration_logs[0].change_type in ("system_prompt", "output_contract")
    assert result.final_agent.retrieval_config == agent.retrieval_config
    assert result.final_agent.selected_tools == agent.selected_tools
    assert len(gateway.calls) == 1


@pytest.mark.unit
async def test_optimizer_stops_at_max_3_iterations() -> None:
    gateway = FakePatchLLMGateway()
    optimizer = CriticOptimizerService(llm_gateway=gateway, max_iterations=3, min_delta=0.02)
    agent = _make_agent()

    # Pass rate improves by 0.10 each time (10/20 -> 12/20 -> 14/20 -> 16/20), never hitting 0.90
    eval_round = 0

    async def evaluate_fn(candidate: AgentDefinition) -> list[JudgeScore]:
        nonlocal eval_round
        passed_count = 10 + (eval_round * 2)
        eval_round += 1
        cats = [FailureCategory.NONE] * passed_count + [FailureCategory.RETRIEVAL_MISS] * (
            20 - passed_count
        )
        _, scores = _make_scores(cats, agent.project_id)
        return scores

    result = await optimizer.optimize(agent=agent, evaluate_fn=evaluate_fn)

    assert len(result.iteration_logs) == 3
    assert result.stop_reason == "max_iterations_reached"


@pytest.mark.unit
async def test_optimizer_stops_early_on_diminishing_returns() -> None:
    gateway = FakePatchLLMGateway()
    optimizer = CriticOptimizerService(llm_gateway=gateway, max_iterations=3, min_delta=0.02)
    agent = _make_agent()

    # Pass rate stays flat at 0.50 -> delta 0.0 < 0.02
    async def evaluate_fn(candidate: AgentDefinition) -> list[JudgeScore]:
        cats = [FailureCategory.NONE] * 5 + [FailureCategory.PROMPT_DEFECT] * 5
        _, scores = _make_scores(cats, agent.project_id)
        return scores

    result = await optimizer.optimize(agent=agent, evaluate_fn=evaluate_fn)

    assert len(result.iteration_logs) == 1
    assert result.stop_reason == "diminishing_returns"


@pytest.mark.unit
async def test_optimizer_stops_early_on_budget_cap() -> None:
    gateway = FakePatchLLMGateway()
    optimizer = CriticOptimizerService(llm_gateway=gateway, min_call_budget=25)
    agent = _make_agent()

    async def evaluate_fn(candidate: AgentDefinition) -> list[JudgeScore]:
        cats = [FailureCategory.NONE] * 5 + [FailureCategory.PROMPT_DEFECT] * 5
        _, scores = _make_scores(cats, agent.project_id)
        return scores

    result = await optimizer.optimize(
        agent=agent,
        evaluate_fn=evaluate_fn,
        remaining_call_budget=10,
    )

    assert len(result.iteration_logs) == 0
    assert result.stop_reason == "budget_cap_reached"
