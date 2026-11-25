from __future__ import annotations

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from app.domain.entities.agent_definition import (
    AgentDefinition,
    OutputContract,
    RetrievalConfig,
)
from app.domain.entities.conversation import Conversation, Message
from app.domain.entities.evaluation import (
    EvalCase,
    EvalRun,
    HonestReport,
    IterationLog,
    JudgeScore,
)
from app.domain.value_objects.enums import (
    EvalCaseType,
    FailureCategory,
    RunStatus,
    ToolName,
)


@pytest.mark.unit
def test_retrieval_config_and_output_contract_are_immutable() -> None:
    retrieval = RetrievalConfig()
    assert retrieval.chunk_size == 600
    assert retrieval.top_k == 5
    with pytest.raises(FrozenInstanceError):
        retrieval.top_k = 10  # type: ignore[misc]

    contract = OutputContract(refusal_template="I cannot answer that.")
    assert contract.format == "markdown"
    assert contract.require_citations is True
    with pytest.raises(FrozenInstanceError):
        contract.max_response_words = 500  # type: ignore[misc]


@pytest.mark.unit
def test_agent_definition_bump_version() -> None:
    agent = AgentDefinition(
        id=uuid4(),
        project_id=uuid4(),
        slug="hr-assistant",
        version=1,
        system_prompt="You are a helpful HR assistant that only answers from context.",
        retrieval_config=RetrievalConfig(),
        selected_tools=[ToolName.CURRENT_DATE],
        output_contract=OutputContract(refusal_template="Sorry, out of scope."),
    )
    new_retrieval = RetrievalConfig(top_k=8, similarity_threshold=0.25)
    bumped = agent.bump_version(
        system_prompt="You are a strict HR assistant. Cite every policy claim.",
        retrieval_config=new_retrieval,
    )

    assert bumped.version == 2
    assert agent.version == 1
    assert bumped.id == agent.id
    assert bumped.project_id == agent.project_id
    assert bumped.slug == agent.slug
    assert bumped.retrieval_config.top_k == 8
    assert bumped.selected_tools == [ToolName.CURRENT_DATE]
    assert bumped.output_contract == agent.output_contract


@pytest.mark.unit
def test_iteration_log_enforces_bounds() -> None:
    log = IterationLog(
        iteration=1,
        score_before=0.65,
        score_after=0.85,
        failures_addressed=[uuid4()],
        change_type="retrieval_config",
        what_changed="Increased top_k from 5 to 8",
        why="Two eval cases failed due to retrieval_miss.",
    )
    assert log.iteration == 1

    with pytest.raises(ValueError, match="iteration"):
        IterationLog(
            iteration=0,
            score_before=0.5,
            score_after=0.6,
            failures_addressed=[],
            change_type="system_prompt",
            what_changed="Adjusted prompt",
            why="Test lower bound",
        )

    with pytest.raises(ValueError, match="iteration"):
        IterationLog(
            iteration=4,
            score_before=0.8,
            score_after=0.9,
            failures_addressed=[],
            change_type="system_prompt",
            what_changed="Adjusted prompt",
            why="Test upper bound",
        )


@pytest.mark.unit
def test_eval_case_judge_score_eval_run_and_honest_report() -> None:
    project_id = uuid4()
    case_id = uuid4()
    eval_case = EvalCase(
        id=case_id,
        project_id=project_id,
        case_type=EvalCaseType.ANSWERABLE,
        question="How many PTO days do employees get?",
        expected_sources=["policy.pdf"],
        expected_facts=["20 days"],
        should_refuse=False,
        rationale="Directly stated in section 2.",
    )
    score = JudgeScore(
        eval_case_id=eval_case.id,
        grounded=True,
        correct=True,
        refusal_accurate=True,
        passed=True,
        failure_category=FailureCategory.NONE,
        reasoning="Answer cites policy.pdf and states 20 days.",
        deterministic_checks={"has_citation": True},
    )
    status = next(iter(RunStatus))
    eval_run = EvalRun(
        id=uuid4(),
        project_id=project_id,
        agent_version=1,
        iteration=1,
        overall_score=1.0,
        pass_rate=1.0,
        status=status,
        scores=[score],
    )
    assert eval_run.pass_rate == 1.0
    assert len(eval_run.scores) == 1

    report = HonestReport(
        project_id=project_id,
        final_agent_version=2,
        per_iteration_scores=[
            {"iteration": 1, "pass_rate": 0.8},
            {"iteration": 2, "pass_rate": 0.95},
        ],
        final_pass_rate=0.95,
        remaining_failures=[{"case_id": str(case_id), "reason": "Edge case ambiguity"}],
        known_limitations=["No 401k policy document provided."],
        recommendation="Ready for internal pilot with 401k disclaimer.",
    )
    assert report.final_pass_rate == 0.95


@pytest.mark.unit
def test_conversation_and_message() -> None:
    conv = Conversation(
        id=uuid4(),
        project_id=uuid4(),
        agent_id=None,
        user_id=uuid4(),
        title="HR Bot Builder",
    )
    msg = Message(
        id=uuid4(),
        conversation_id=conv.id,
        role="user",
        content="Build an HR policy assistant.",
    )
    assert msg.conversation_id == conv.id
    assert msg.role == "user"
    assert msg.metadata == {}
