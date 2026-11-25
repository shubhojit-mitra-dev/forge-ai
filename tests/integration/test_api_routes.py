"""Integration tests for ForgeAI FastAPI routes using TestClient (strict TDD)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.application.container import AppContainer, ParserBundle
from app.application.services.chat_runner_service import ChatRunnerService
from app.application.services.critic_optimizer import CriticOptimizerService
from app.application.services.document_service import DocumentService
from app.application.services.groundability_service import GroundabilityService
from app.application.services.intake_service import IntakeService
from app.application.services.judge_service import JudgeService
from app.application.services.reporter_service import ReporterService
from app.config import Settings
from app.domain.entities.agent_definition import AgentDefinition, OutputContract, RetrievalConfig
from app.domain.entities.document import Document, DocumentChunk
from app.domain.entities.evaluation import EvalCase, HonestReport, IterationLog, JudgeScore
from app.domain.entities.requirements import (
    ClarifyingQA,
    GroundabilityReport,
    RequirementsDoc,
    TopicGroundability,
)
from app.domain.protocols.llm_gateway import LLMResponse
from app.domain.value_objects.enums import EvalCaseType, RunStatus
from app.infrastructure.cache.ttl_cache import InMemoryTTLCache
from app.infrastructure.parsers import CsvParser, OverlapChunker, PdfParser, TextParser
from app.infrastructure.tools.registry import ToolRegistry
from app.presentation.dependencies import (
    UserContext,
    get_agent_repo,
    get_chat_repo,
    get_chat_runner_service,
    get_container,
    get_current_user,
    get_document_repo,
    get_document_service,
    get_eval_repo,
    get_groundability_service,
    get_intake_service,
    get_pipeline_orchestrator,
    get_project_repo,
    get_storage_adapter,
    get_vector_store,
)
from app.presentation.main import create_app

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.domain.entities.conversation import Conversation, Message
    from app.domain.entities.project import ForgeProject


class FakeProjectRepo:
    def __init__(self) -> None:
        self.projects: dict[UUID, ForgeProject] = {}

    async def create(self, project: ForgeProject) -> ForgeProject:
        self.projects[project.id] = project
        return project

    async def get_by_id(self, project_id: UUID) -> ForgeProject | None:
        return self.projects.get(project_id)

    async def list_by_user(self, user_id: UUID) -> list[ForgeProject]:
        return [p for p in self.projects.values() if p.user_id == user_id]

    async def update(self, project: ForgeProject) -> ForgeProject:
        self.projects[project.id] = project
        return project


class FakeDocumentRepo:
    def __init__(self) -> None:
        self.docs: dict[UUID, Document] = {}

    async def create(self, document: Document) -> Document:
        self.docs[document.id] = document
        return document

    async def get_by_id(self, document_id: UUID) -> Document | None:
        return self.docs.get(document_id)

    async def list_by_project(self, project_id: UUID) -> list[Document]:
        return [d for d in self.docs.values() if d.project_id == project_id]

    async def get_by_hash(self, project_id: UUID, content_hash: str) -> Document | None:
        for d in self.docs.values():
            if d.project_id == project_id and d.content_hash == content_hash:
                return d
        return None


class FakeAgentRepo:
    def __init__(self) -> None:
        self.agents: list[AgentDefinition] = []

    async def save(self, agent: AgentDefinition) -> AgentDefinition:
        self.agents.append(agent)
        return agent

    async def get_latest(self, project_id: UUID) -> AgentDefinition | None:
        matching = [a for a in self.agents if a.project_id == project_id]
        return max(matching, key=lambda a: a.version) if matching else None

    async def get_by_slug(self, slug: str) -> AgentDefinition | None:
        matching = [a for a in self.agents if a.slug == slug and a.is_published]
        return max(matching, key=lambda a: a.version) if matching else None

    async def list_versions(self, project_id: UUID) -> list[AgentDefinition]:
        return [a for a in self.agents if a.project_id == project_id]


class FakeEvalRepo:
    def __init__(self) -> None:
        self.cases: dict[UUID, list[EvalCase]] = {}
        self.logs: dict[UUID, list[IterationLog]] = {}
        self.reports: dict[UUID, HonestReport] = {}

    async def save_eval_cases(self, project_id: UUID, cases: list[EvalCase]) -> None:
        self.cases[project_id] = cases

    async def list_eval_cases(self, project_id: UUID) -> list[EvalCase]:
        return self.cases.get(project_id, [])

    async def save_judge_scores(
        self,
        project_id: UUID,
        iteration: int,
        scores: list[JudgeScore],
    ) -> None:
        return None

    async def save_iteration_log(self, project_id: UUID, log: IterationLog) -> None:
        self.logs.setdefault(project_id, []).append(log)

    async def list_iteration_logs(self, project_id: UUID) -> list[IterationLog]:
        return self.logs.get(project_id, [])

    async def save_honest_report(self, report: HonestReport) -> None:
        self.reports[report.project_id] = report

    async def get_honest_report(self, project_id: UUID) -> HonestReport | None:
        return self.reports.get(project_id)


class FakeChatRepo:
    def __init__(self) -> None:
        self.conversations: dict[UUID, Conversation] = {}
        self.messages: dict[UUID, list[Message]] = {}

    async def create_conversation(self, conversation: Conversation) -> Conversation:
        self.conversations[conversation.id] = conversation
        return conversation

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        return self.conversations.get(conversation_id)

    async def add_message(self, message: Message) -> Message:
        self.messages.setdefault(message.conversation_id, []).append(message)
        return message

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        return self.messages.get(conversation_id, [])


class FakeStorageAdapter:
    async def upload(self, path: str, content: bytes, content_type: str = "") -> str:
        return path


class FakeVectorStore:
    def __init__(self) -> None:
        self.chunks: list[DocumentChunk] = []

    async def upsert_chunks(self, chunks: list[DocumentChunk]) -> None:
        self.chunks.extend(chunks)

    async def hybrid_search(
        self,
        project_id: UUID,
        query_text: str,
        query_embedding: list[float],
        top_k: int = 5,
        similarity_threshold: float = 0.35,
    ) -> list[DocumentChunk]:
        matching = [c for c in self.chunks if c.project_id == project_id]
        if not matching:
            matching = [
                DocumentChunk(
                    id=uuid4(),
                    document_id=uuid4(),
                    project_id=project_id,
                    chunk_index=0,
                    content="Employees receive 20 days of annual PTO.",
                    content_hash="h1",
                    token_count=8,
                    metadata={"filename": "handbook.md"},
                    similarity=0.9,
                )
            ]
        return matching[:top_k]


class FakeEmbeddingGateway:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeLLMGateway:
    def __init__(self) -> None:
        self.mode = "chat"

    async def complete(
        self,
        messages: list[dict[str, str]],
        tier: str = "orchestrator-primary",
        temperature: float = 0.0,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            content="Employees receive 20 days of annual PTO.",
            model="fake-model",
            prompt_tokens=10,
            completion_tokens=10,
            latency_ms=5,
        )


class FakeIntakeService(IntakeService):
    def __init__(self) -> None:
        pass

    async def generate_questions(self, brief: str, doc_summaries: list[str]) -> list[str]:
        return ["Who is the target audience?", "What tone should the agent use?"]

    async def finalize_requirements(
        self,
        brief: str,
        doc_summaries: list[str],
        qa_pairs: list[ClarifyingQA],
    ) -> RequirementsDoc:
        return RequirementsDoc(
            agent_name="HR Policy Assistant",
            scope="Answer employee HR policy questions from the handbook.",
            target_audience="Employees",
            tone="Professional and concise",
            must_answer_topics=["PTO policy"],
            must_refuse_topics=["Executive compensation"],
            clarifying_qa=qa_pairs,
            detected_tool_needs=[],
        )


class FakeGroundabilityService(GroundabilityService):
    def __init__(self) -> None:
        pass

    async def evaluate(
        self,
        project_id: UUID,
        requirements: RequirementsDoc,
    ) -> GroundabilityReport:
        return GroundabilityReport(
            is_passable=True,
            critical_gaps=[],
            warnings=[
                TopicGroundability(
                    topic="PTO policy",
                    is_grounded=True,
                    confidence=0.92,
                    supporting_documents=["handbook.md"],
                )
            ],
            summary="All 1 required topics are grounded in the uploaded documents.",
        )


class FakePipelineOrchestrator:
    def __init__(
        self,
        project_repo: FakeProjectRepo,
        agent_repo: FakeAgentRepo,
        eval_repo: FakeEvalRepo,
    ) -> None:
        self._project_repo = project_repo
        self._agent_repo = agent_repo
        self._eval_repo = eval_repo

    async def run(
        self,
        *,
        project_id: UUID,
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> HonestReport:
        if on_event is not None:
            await on_event({"event": "stage_started", "stage": "agent_generation"})
            await on_event(
                {
                    "event": "eval_scored",
                    "iteration": 1,
                    "eval_case_id": str(uuid4()),
                    "passed": True,
                    "failure_category": "none",
                }
            )
            await on_event(
                {
                    "event": "iteration_complete",
                    "iteration": 1,
                    "score_before": 0.5,
                    "score_after": 1.0,
                    "change_type": "system_prompt",
                }
            )

        agent = AgentDefinition(
            id=uuid4(),
            project_id=project_id,
            slug="hr-policy-assistant",
            version=1,
            system_prompt="You are an HR Policy Assistant grounded strictly in company documents.",
            retrieval_config=RetrievalConfig(),
            selected_tools=[],
            output_contract=OutputContract(),
            is_published=True,
        )
        await self._agent_repo.save(agent)
        await self._eval_repo.save_eval_cases(
            project_id,
            [
                EvalCase(
                    id=uuid4(),
                    project_id=project_id,
                    case_type=EvalCaseType.ANSWERABLE,
                    question="How many PTO days?",
                    expected_sources=["handbook.md"],
                    expected_facts=["20 days"],
                    should_refuse=False,
                    rationale="Direct policy fact",
                )
            ],
        )
        report = HonestReport(
            project_id=project_id,
            final_agent_version=1,
            per_iteration_scores=[{"iteration": 1, "pass_rate": 1.0}],
            final_pass_rate=1.0,
            remaining_failures=[],
            known_limitations=[],
            recommendation="Ready for production.",
        )
        await self._eval_repo.save_honest_report(report)
        project = await self._project_repo.get_by_id(project_id)
        if project is not None:
            project.status = RunStatus.COMPLETED
            await self._project_repo.update(project)

        if on_event is not None:
            await on_event(
                {
                    "event": "forge_finished",
                    "final_pass_rate": 1.0,
                    "final_agent_version": 1,
                    "stop_reason": "target_reached",
                }
            )
        return report


@pytest.fixture()
def api_client() -> tuple[TestClient, dict[str, Any]]:
    user_id = uuid4()
    fake_llm = FakeLLMGateway()
    fake_embeddings = FakeEmbeddingGateway()
    fake_vector_store = FakeVectorStore()
    fake_project_repo = FakeProjectRepo()
    fake_document_repo = FakeDocumentRepo()
    fake_agent_repo = FakeAgentRepo()
    fake_eval_repo = FakeEvalRepo()
    fake_chat_repo = FakeChatRepo()
    fake_storage = FakeStorageAdapter()
    tool_registry = ToolRegistry()

    parsers = ParserBundle(
        pdf=PdfParser(),
        csv=CsvParser(),
        text=TextParser(),
        chunker=OverlapChunker(),
    )
    container = AppContainer(
        settings=Settings(cors_origins=["http://localhost:3000"]),
        cache=InMemoryTTLCache(),
        llm_gateway=fake_llm,  # type: ignore[arg-type]
        embedding_gateway=fake_embeddings,  # type: ignore[arg-type]
        tool_registry=tool_registry,
        parsers=parsers,
        judge_service=JudgeService(llm_gateway=fake_llm),
        critic_optimizer=CriticOptimizerService(llm_gateway=fake_llm),
        reporter_service=ReporterService(),
    )
    doc_service = DocumentService(
        parsers=[parsers.pdf, parsers.csv, parsers.text],
        chunker=parsers.chunker,
        embedding_gateway=fake_embeddings,
        vector_store=fake_vector_store,
    )
    chat_runner = ChatRunnerService(
        llm_gateway=fake_llm,
        embedding_gateway=fake_embeddings,
        vector_store=fake_vector_store,
        tool_registry=tool_registry,
    )
    orchestrator = FakePipelineOrchestrator(fake_project_repo, fake_agent_repo, fake_eval_repo)

    app = create_app()
    app.dependency_overrides[get_container] = lambda: container
    app.dependency_overrides[get_current_user] = lambda: UserContext(
        user_id=user_id, email="tester@forgeai.dev"
    )
    app.dependency_overrides[get_project_repo] = lambda: fake_project_repo
    app.dependency_overrides[get_document_repo] = lambda: fake_document_repo
    app.dependency_overrides[get_agent_repo] = lambda: fake_agent_repo
    app.dependency_overrides[get_eval_repo] = lambda: fake_eval_repo
    app.dependency_overrides[get_chat_repo] = lambda: fake_chat_repo
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_vector_store] = lambda: fake_vector_store
    app.dependency_overrides[get_document_service] = lambda: doc_service
    app.dependency_overrides[get_intake_service] = lambda: FakeIntakeService()
    app.dependency_overrides[get_groundability_service] = lambda: FakeGroundabilityService()
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_chat_runner_service] = lambda: chat_runner

    return TestClient(app), {
        "user_id": user_id,
        "agent_repo": fake_agent_repo,
        "project_repo": fake_project_repo,
    }


@pytest.mark.integration
def test_health_endpoint(api_client: tuple[TestClient, dict[str, Any]]) -> None:
    client, _ = api_client
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ok", "degraded"}
    assert "environment" in body


@pytest.mark.integration
def test_full_project_intake_forge_artifacts_and_public_chat_flow(
    api_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, _ = api_client

    # 1. Create project
    create_resp = client.post(
        "/api/v1/projects",
        json={
            "title": "HR Policy Bot",
            "brief": "Build an HR policy assistant that answers PTO and benefits questions.",
        },
    )
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    # 2. List & get project
    list_resp = client.get("/api/v1/projects")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    get_resp = client.get(f"/api/v1/projects/{project_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["project"]["id"] == project_id

    # 3. Upload document
    upload_resp = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files={"file": ("handbook.md", b"# PTO\nEmployees get 20 days of PTO.", "text/markdown")},
    )
    assert upload_resp.status_code == 201
    assert upload_resp.json()["filename"] == "handbook.md"
    assert upload_resp.json()["chunk_count"] >= 1

    # 4. Intake start & submit
    start_resp = client.post(f"/api/v1/projects/{project_id}/intake/start")
    assert start_resp.status_code == 200
    assert len(start_resp.json()["questions"]) == 2

    submit_resp = client.post(
        f"/api/v1/projects/{project_id}/intake/submit",
        json={
            "qa_pairs": [
                {"question": "Who is the target audience?", "answer": "All full-time employees."}
            ]
        },
    )
    assert submit_resp.status_code == 200
    assert submit_resp.json()["groundability"]["is_passable"] is True

    # 5. Forge run
    run_resp = client.post(f"/api/v1/projects/{project_id}/forge/run")
    assert run_resp.status_code == 200
    assert run_resp.json()["final_pass_rate"] == 1.0

    # 6. Forge SSE stream
    with client.stream("GET", f"/api/v1/projects/{project_id}/forge/stream") as stream_resp:
        assert stream_resp.status_code == 200
        raw_stream = "".join(stream_resp.iter_text())
    assert "stage_started" in raw_stream
    assert "forge_finished" in raw_stream

    # 7. Artifacts export
    artifacts_resp = client.get(f"/api/v1/projects/{project_id}/artifacts")
    assert artifacts_resp.status_code == 200
    artifacts = artifacts_resp.json()
    assert artifacts["agent_definition"]["slug"] == "hr-policy-assistant"
    assert "# ForgeAI Honest Report" in artifacts["honest_report_markdown"]

    # 8. Public agent metadata & chat
    meta_resp = client.get("/api/v1/agents/public/hr-policy-assistant")
    assert meta_resp.status_code == 200
    assert meta_resp.json()["slug"] == "hr-policy-assistant"

    chat_resp = client.post(
        "/api/v1/agents/public/hr-policy-assistant/chat",
        json={"message": "How many PTO days do employees get?"},
    )
    assert chat_resp.status_code == 200
    chat_body = chat_resp.json()
    assert "20 days" in chat_body["answer"]
    assert "handbook.md" in chat_body["citations"]


@pytest.mark.integration
def test_missing_project_and_agent_return_404(
    api_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, _ = api_client
    missing_id = uuid4()

    proj_resp = client.get(f"/api/v1/projects/{missing_id}")
    assert proj_resp.status_code == 404
    assert json.loads(proj_resp.text)["code"] == "PROJECT_NOT_FOUND"

    agent_resp = client.get("/api/v1/agents/public/non-existent-slug")
    assert agent_resp.status_code == 404
    assert json.loads(agent_resp.text)["code"] == "AGENT_NOT_FOUND"
