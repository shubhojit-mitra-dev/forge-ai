"""Unit tests for Pydantic v2 application DTOs."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.application.dtos import (
    AgentDefinitionDTO,
    ClarifyingQADTO,
    EvalCaseDTO,
    GroundabilityReportDTO,
    HonestReportDTO,
    IterationLogDTO,
    JudgeScoreDTO,
    OutputContractDTO,
    ProjectCreateDTO,
    RequirementsDocDTO,
    RetrievalConfigDTO,
    TopicGroundabilityDTO,
)
from app.domain.value_objects.enums import EvalCaseType, FailureCategory, ToolName


@pytest.mark.unit
def test_project_and_requirements_dtos_enforce_bounds_and_immutability() -> None:
    proj = ProjectCreateDTO(title="HR Policy Bot", brief="Answer shore staff HR policy questions.")
    with pytest.raises(ValidationError):
        proj.title = "Mutated"  # type: ignore[misc]

    req = RequirementsDocDTO(
        agent_name="HR Assistant",
        scope="Answer shore staff HR leave and travel policies.",
        target_audience="Shore staff",
        tone="Professional",
        must_answer_topics=["Annual leave"],
        must_refuse_topics=["Salary negotiation"],
        clarifying_qa=[ClarifyingQADTO(question="Which region?", answer="Global")],
        detected_tool_needs=[ToolName.CURRENT_DATE],
    )
    assert req.agent_name == "HR Assistant"

    with pytest.raises(ValidationError):
        RequirementsDocDTO(
            agent_name="HR Assistant",
            scope="Answer shore staff HR leave and travel policies.",
            target_audience="Shore staff",
            tone="Professional",
            must_answer_topics=["Annual leave"],
            must_refuse_topics=["Salary negotiation"],
            clarifying_qa=[ClarifyingQADTO(question=f"Q{i}", answer="A") for i in range(6)],
            detected_tool_needs=[],
        )

    topic = TopicGroundabilityDTO(
        topic="Annual leave",
        is_grounded=True,
        confidence=0.92,
        supporting_documents=["leave_policy.pdf"],
    )
    report = GroundabilityReportDTO(
        is_passable=True,
        critical_gaps=[],
        warnings=[],
        summary="All topics grounded.",
    )
    assert topic.is_grounded and report.is_passable


@pytest.mark.unit
def test_agent_and_eval_dtos_validate_constraints() -> None:
    retrieval = RetrievalConfigDTO(chunk_size=600, chunk_overlap=100, top_k=5)
    contract = OutputContractDTO(
        format="markdown",
        require_citations=True,
        refusal_template="I cannot answer that based on the provided documents.",
        max_response_words=350,
    )
    agent = AgentDefinitionDTO(
        id=uuid4(),
        project_id=uuid4(),
        slug="hr-policy-1234",
        version=1,
        system_prompt="You are a helpful HR policy assistant grounded strictly in uploaded PDFs.",
        retrieval_config=retrieval,
        selected_tools=[ToolName.CURRENT_DATE],
        output_contract=contract,
    )
    assert agent.version == 1

    eval_case = EvalCaseDTO(
        id=uuid4(),
        case_type=EvalCaseType.ANSWERABLE,
        question="How many days of annual leave are granted?",
        expected_sources=["leave_policy.pdf"],
        expected_facts=["20 days"],
        should_refuse=False,
        rationale="Direct policy lookup.",
    )
    score = JudgeScoreDTO(
        eval_case_id=eval_case.id,
        grounded=True,
        correct=True,
        refusal_accurate=True,
        passed=True,
        failure_category=FailureCategory.NONE,
        reasoning="Grounded in leave_policy.pdf.",
        deterministic_checks={"citation_present": True},
    )
    iter_log = IterationLogDTO(
        iteration=1,
        score_before=0.70,
        score_after=0.85,
        failures_addressed=[eval_case.id],
        change_type="retrieval_config",
        what_changed="Increased top_k from 5 to 8.",
        why="Address retrieval_miss failures.",
    )
    honest = HonestReportDTO(
        project_id=agent.project_id,
        final_agent_version=2,
        per_iteration_scores=[{"iteration": 1, "pass_rate": 0.85}],
        final_pass_rate=0.85,
        remaining_failures=[],
        known_limitations=["Requires explicit policy PDFs."],
        recommendation="Ready for pilot.",
    )
    assert score.passed and iter_log.iteration == 1 and honest.final_pass_rate == 0.85

    with pytest.raises(ValidationError):
        IterationLogDTO(
            iteration=4,
            score_before=0.7,
            score_after=0.8,
            failures_addressed=[],
            change_type="system_prompt",
            what_changed="x",
            why="y",
        )

