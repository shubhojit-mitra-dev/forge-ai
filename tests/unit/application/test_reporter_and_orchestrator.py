"""Unit tests for ReporterService, PipelineOrchestrator, and AppContainer."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.container import AppContainer, build_container
from app.application.services.critic_optimizer import CriticOptimizerService
from app.application.services.judge_service import JudgeService
from app.application.services.pipeline_orchestrator import PipelineOrchestrator
from app.application.services.reporter_service import ReporterService
from app.domain.entities.agent_definition import (
    AgentDefinition,
    OutputContract,
    RetrievalConfig,
)
from app.domain.entities.document import DocumentChunk
from app.domain.entities.evaluation import (
    EvalCase,
    HonestReport,
    IterationLog,
    JudgeScore,
)
from app.domain.entities.project import ForgeProject
from app.domain.entities.requirements import RequirementsDoc
from app.domain.protocols.llm_gateway import LLMResponse
from app.domain.value_objects.enums import (
    EvalCaseType,
    FailureCategory,
    RunStatus,
    ToolName,
)


class FakeAgentGenerator:
    """Stub AgentGenerator returning a v1 AgentDefinition."""

    def __init__(self, agent: AgentDefinition) -> None:
        self._agent = agent

    async def generate(
        self,
        project_id: UUID,
        requirements: RequirementsDoc,
        slug: str | None = None,
    ) -> AgentDefinition:
        return self._agent


class FakeEvalGenerator:
    """Stub EvalGenerator returning a list of EvalCase."""

    def __init__(self, cases: list[EvalCase]) -> None:
        self._cases = cases

    async def generate(
        self,
        project_id: UUID,
        requirements: RequirementsDoc,
        chunks: list[DocumentChunk] | None = None,
    ) -> list[EvalCase]:
        return self._cases


class FakeEmbeddingGateway:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 4 for _ in texts]


class FakeVectorStore:
    def __init__(self, chunks: list[DocumentChunk]) -> None:
        self._chunks = chunks

    async def upsert_chunks(self, chunks: list[DocumentChunk]) -> None:
        self._chunks.extend(chunks)

    async def hybrid_search(
        self,
        project_id: UUID,
        query_text: str,
        query_embedding: list[float],
        top_k: int = 5,
        similarity_threshold: float = 0.35,
    ) -> list[DocumentChunk]:
        return self._chunks[:top_k]


class FakeOrchestratorLLMGateway:
    """Routes agent vs judge vs critic calls deterministically."""

    async def complete(
        self,
        messages: list[dict[str, str]],
        tier: str = "orchestrator-primary",
        temperature: float = 0.0,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        if tier == "fast-judge":
            return LLMResponse(
                content=json.dumps(
                    {
                        "grounded": True,
                        "correct": True,
                        "refusal_accurate": True,
                        "failure_category": "none",
                        "reasoning": "Accurate and cited.",
                    }
                ),
                model="gemini-2.5-flash-lite",
                prompt_tokens=80,
                completion_tokens=30,
                latency_ms=10,
            )
        return LLMResponse(
            content="According to policy.pdf, PTO is 15 days per year.",
            model="gpt-oss-20b",
            prompt_tokens=90,
            completion_tokens=20,
            latency_ms=15,
        )


class InMemoryProjectRepo:
    def __init__(self, project: ForgeProject) -> None:
        self.project = project

    async def create(self, project: ForgeProject) -> ForgeProject:
        self.project = project
        return project

    async def get_by_id(self, project_id: UUID) -> ForgeProject | None:
        return self.project if self.project.id == project_id else None

    async def list_by_user(self, user_id: UUID) -> list[ForgeProject]:
        return [self.project]

    async def update(self, project: ForgeProject) -> ForgeProject:
        self.project = project
        return project


class InMemoryAgentRepo:
    def __init__(self) -> None:
        self.saved: list[AgentDefinition] = []

    async def save(self, agent: AgentDefinition) -> AgentDefinition:
        self.saved.append(agent)
        return agent

    async def get_latest(self, project_id: UUID) -> AgentDefinition | None:
        return self.saved[-1] if self.saved else None

    async def get_by_slug(self, slug: str) -> AgentDefinition | None:
        return next((a for a in reversed(self.saved) if a.slug == slug), None)

    async def list_versions(self, project_id: UUID) -> list[AgentDefinition]:
        return list(self.saved)


class InMemoryEvalRepo:
    def __init__(self) -> None:
        self.cases: list[EvalCase] = []
        self.scores_by_iter: dict[int, list[JudgeScore]] = {}
        self.logs: list[IterationLog] = []
        self.report: HonestReport | None = None

    async def save_eval_cases(self, project_id: UUID, cases: list[EvalCase]) -> None:
        self.cases = list(cases)

    async def list_eval_cases(self, project_id: UUID) -> list[EvalCase]:
        return list(self.cases)

    async def save_judge_scores(
        self, project_id: UUID, iteration: int, scores: list[JudgeScore]
    ) -> None:
        self.scores_by_iter[iteration] = list(scores)

    async def save_iteration_log(self, project_id: UUID, log: IterationLog) -> None:
        self.logs.append(log)

    async def list_iteration_logs(self, project_id: UUID) -> list[IterationLog]:
        return list(self.logs)

    async def save_honest_report(self, report: HonestReport) -> None:
        self.report = report

    async def get_honest_report(self, project_id: UUID) -> HonestReport | None:
        return self.report


@pytest.mark.unit
def test_reporter_service_compiles_honest_report_without_inflating_scores() -> None:
    project_id = uuid4()
    agent = AgentDefinition(
        id=uuid4(),
        project_id=project_id,
        slug="hr-bot",
        version=2,
        system_prompt="You are an HR assistant. Cite sources and refuse out-of-scope queries.",
        retrieval_config=RetrievalConfig(),
        selected_tools=[],
        output_contract=OutputContract(),
    )
    case_pass = EvalCase(
        id=uuid4(),
        project_id=project_id,
        case_type=EvalCaseType.ANSWERABLE,
        question="What is the PTO policy?",
        expected_sources=["policy.pdf"],
        expected_facts=["15 days"],
        should_refuse=False,
        rationale="PTO",
    )
    case_fail = EvalCase(
        id=uuid4(),
        project_id=project_id,
        case_type=EvalCaseType.REFUSAL,
        question="What is the CEO bonus?",
        expected_sources=[],
        expected_facts=[],
        should_refuse=True,
        rationale="Out of scope",
    )
    scores = [
        JudgeScore(
            eval_case_id=case_pass.id,
            grounded=True,
            correct=True,
            refusal_accurate=True,
            passed=True,
            failure_category=FailureCategory.NONE,
            reasoning="Good.",
        ),
        JudgeScore(
            eval_case_id=case_fail.id,
            grounded=False,
            correct=False,
            refusal_accurate=False,
            passed=False,
            failure_category=FailureCategory.WRONG_REFUSAL,
            reasoning="Answered instead of refusing.",
        ),
    ]
    logs = [
        IterationLog(
            iteration=1,
            score_before=0.25,
            score_after=0.50,
            failures_addressed=[case_fail.id],
            change_type="system_prompt",
            what_changed="Added refusal boundary.",
            why="Reduce wrong_refusal.",
        )
    ]

    reporter = ReporterService()
    report = reporter.compile_report(
        project_id=project_id,
        final_agent=agent,
        iteration_logs=logs,
        final_scores=scores,
        eval_cases=[case_pass, case_fail],
        stop_reason="diminishing_returns",
    )

    assert report.final_agent_version == 2
    assert report.final_pass_rate == pytest.approx(0.5)
    assert len(report.remaining_failures) == 1
    assert report.remaining_failures[0]["failure_category"] == "wrong_refusal"
    assert report.remaining_failures[0]["eval_case_id"] == str(case_fail.id)
    assert len(report.per_iteration_scores) == 1
    assert any(
        "diminishing" in lim.lower() or "refusal" in lim.lower() for lim in report.known_limitations
    )


@pytest.mark.unit
async def test_pipeline_orchestrator_runs_end_to_end_with_mocked_boundaries() -> None:
    project_id = uuid4()
    req = RequirementsDoc(
        agent_name="HR Policy Bot",
        scope="Answer employee HR policy questions from uploaded documents.",
        target_audience="Employees",
        tone="professional",
        must_answer_topics=["PTO allowance"],
        must_refuse_topics=["Executive compensation"],
        clarifying_qa=[],
        detected_tool_needs=[],
    )
    project = ForgeProject(
        id=project_id,
        user_id=uuid4(),
        title="HR Bot",
        brief="Build an HR policy assistant.",
        status=RunStatus.PENDING,
        requirements_doc=req,
    )
    agent = AgentDefinition(
        id=uuid4(),
        project_id=project_id,
        slug="hr-bot",
        version=1,
        system_prompt="You are an HR assistant. Cite policy.pdf and state exact PTO numbers.",
        retrieval_config=RetrievalConfig(),
        selected_tools=[ToolName.CURRENT_DATE],
        output_contract=OutputContract(require_citations=True, max_response_words=150),
    )
    cases = [
        EvalCase(
            id=uuid4(),
            project_id=project_id,
            case_type=EvalCaseType.ANSWERABLE,
            question=f"What is PTO policy {i}?",
            expected_sources=["policy.pdf"],
            expected_facts=["15 days per year"],
            should_refuse=False,
            rationale="HR PTO",
        )
        for i in range(4)
    ]
    chunks = [
        DocumentChunk(
            id=uuid4(),
            document_id=uuid4(),
            project_id=project_id,
            chunk_index=0,
            content="PTO allowance is 15 days per year.",
            content_hash="h0",
            token_count=8,
            metadata={"filename": "policy.pdf"},
        )
    ]

    llm_gateway = FakeOrchestratorLLMGateway()
    judge = JudgeService(
        llm_gateway=llm_gateway, judge_tier="fast-judge", agent_model="gpt-oss-20b"
    )
    optimizer = CriticOptimizerService(llm_gateway=llm_gateway)
    reporter = ReporterService()
    project_repo = InMemoryProjectRepo(project)
    agent_repo = InMemoryAgentRepo()
    eval_repo = InMemoryEvalRepo()
    events: list[dict[str, Any]] = []

    async def on_event(evt: dict[str, Any]) -> None:
        events.append(evt)

    orchestrator = PipelineOrchestrator(
        agent_generator=FakeAgentGenerator(agent),
        eval_generator=FakeEvalGenerator(cases),
        llm_gateway=llm_gateway,
        embedding_gateway=FakeEmbeddingGateway(),
        vector_store=FakeVectorStore(chunks),
        judge_service=judge,
        critic_optimizer=optimizer,
        reporter_service=reporter,
        project_repo=project_repo,
        agent_repo=agent_repo,
        eval_repo=eval_repo,
    )

    report = await orchestrator.run(project_id=project_id, on_event=on_event)

    assert report.project_id == project_id
    assert report.final_pass_rate == pytest.approx(1.0)
    assert project_repo.project.status == RunStatus.COMPLETED
    assert len(agent_repo.saved) >= 1
    assert eval_repo.report is not None
    event_types = [e["event"] for e in events]
    assert "stage_started" in event_types
    assert "forge_finished" in event_types


@pytest.mark.unit
def test_build_container_wires_core_dependencies() -> None:
    container = build_container()
    assert isinstance(container, AppContainer)
    assert container.judge_service is not None
    assert container.critic_optimizer is not None
    assert container.reporter_service is not None
    assert container.tool_registry is not None
