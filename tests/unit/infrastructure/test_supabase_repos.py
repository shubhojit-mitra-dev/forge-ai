"""Unit tests for Supabase client, storage, pgvector store, and repositories."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.config import Settings
from app.domain.entities.agent_definition import (
    AgentDefinition,
    OutputContract,
    RetrievalConfig,
)
from app.domain.entities.conversation import Conversation, Message
from app.domain.entities.document import Document, DocumentChunk
from app.domain.entities.evaluation import (
    EvalCase,
    HonestReport,
    IterationLog,
    JudgeScore,
)
from app.domain.entities.project import ForgeProject
from app.domain.entities.requirements import (
    ClarifyingQA,
    GroundabilityReport,
    RequirementsDoc,
    TopicGroundability,
)
from app.domain.exceptions import ValidationDomainError
from app.domain.protocols.repositories import (
    AgentRepositoryProtocol,
    ChatRepositoryProtocol,
    DocumentRepositoryProtocol,
    EvalRepositoryProtocol,
    ProjectRepositoryProtocol,
)
from app.domain.protocols.vector_store import VectorStoreProtocol
from app.domain.value_objects.enums import (
    EvalCaseType,
    FailureCategory,
    RunStatus,
    ToolName,
)
from app.infrastructure.supabase import (
    PgVectorStore,
    SupabaseAgentRepository,
    SupabaseChatRepository,
    SupabaseDocumentRepository,
    SupabaseEvalRepository,
    SupabaseProjectRepository,
    SupabaseStorageAdapter,
    get_supabase_client,
)
from app.infrastructure.supabase.client import clear_supabase_client_cache


def _make_response(data: Any) -> MagicMock:
    response = MagicMock()
    response.data = data
    return response


def _make_table_chain(execute_data: Any) -> MagicMock:
    chain = MagicMock()
    for method in (
        "select",
        "insert",
        "upsert",
        "update",
        "delete",
        "eq",
        "in_",
        "order",
        "limit",
    ):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = _make_response(execute_data)
    return chain


class TestSupabaseClientFactory:
    def setup_method(self) -> None:
        clear_supabase_client_cache()

    def test_raises_when_config_missing(self) -> None:
        settings = Settings(supabase_url="", supabase_service_role_key="", supabase_anon_key="")
        with pytest.raises(ValidationDomainError) as exc_info:
            get_supabase_client(settings)
        assert exc_info.value.code == "SUPABASE_CONFIG_MISSING"

    def test_caches_client_and_prefers_service_role_key(self) -> None:
        settings = Settings(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-key",
            supabase_anon_key="anon-key",
        )
        fake_client = MagicMock()
        with patch(
            "app.infrastructure.supabase.client.create_client",
            return_value=fake_client,
        ) as mock_create:
            c1 = get_supabase_client(settings)
            c2 = get_supabase_client(settings)

        assert c1 is fake_client
        assert c2 is fake_client
        mock_create.assert_called_once_with("https://example.supabase.co", "service-key")


class TestSupabaseStorageAdapter:
    async def test_upload_download_signed_url_and_delete(self) -> None:
        client = MagicMock()
        bucket = MagicMock()
        client.storage.from_.return_value = bucket
        bucket.download.return_value = b"hello pdf"
        bucket.create_signed_url.return_value = {"signedURL": "https://signed.example/doc.pdf"}

        adapter = SupabaseStorageAdapter(client, bucket_name="forge-documents")

        uploaded_path = await adapter.upload(
            "proj-1/doc.pdf",
            b"hello pdf",
            content_type="application/pdf",
        )
        assert uploaded_path == "proj-1/doc.pdf"
        bucket.upload.assert_called_once()

        downloaded = await adapter.download("proj-1/doc.pdf")
        assert downloaded == b"hello pdf"
        bucket.download.assert_called_once_with("proj-1/doc.pdf")

        signed = await adapter.create_signed_url("proj-1/doc.pdf", expires_in=600)
        assert signed == "https://signed.example/doc.pdf"
        bucket.create_signed_url.assert_called_once_with("proj-1/doc.pdf", 600)

        await adapter.delete("proj-1/doc.pdf")
        bucket.remove.assert_called_once_with(["proj-1/doc.pdf"])


class TestPgVectorStore:
    def test_conforms_to_vector_store_protocol(self) -> None:
        store = PgVectorStore(MagicMock())
        assert isinstance(store, VectorStoreProtocol)

    async def test_upsert_chunks_deduplicates_by_content_hash(self) -> None:
        project_id = uuid4()
        doc_id = uuid4()
        existing_content = "Already embedded chunk"
        existing_hash = hashlib.sha256(existing_content.encode("utf-8")).hexdigest()
        new_content = "Fresh chunk content"
        new_hash = hashlib.sha256(new_content.encode("utf-8")).hexdigest()

        select_chain = _make_table_chain([{"content_hash": existing_hash}])
        upsert_chain = _make_table_chain([])
        table_mock = MagicMock()
        table_mock.select.return_value = select_chain
        table_mock.upsert.return_value = upsert_chain

        client = MagicMock()
        client.table.return_value = table_mock

        store = PgVectorStore(client)
        chunks = [
            DocumentChunk(
                id=uuid4(),
                document_id=doc_id,
                project_id=project_id,
                chunk_index=0,
                content=existing_content,
                content_hash="",  # verify auto sha256 computation
                token_count=4,
                embedding=[0.1, 0.2],
            ),
            DocumentChunk(
                id=uuid4(),
                document_id=doc_id,
                project_id=project_id,
                chunk_index=1,
                content=new_content,
                content_hash=new_hash,
                token_count=3,
                embedding=[0.3, 0.4],
            ),
            DocumentChunk(
                id=uuid4(),
                document_id=doc_id,
                project_id=project_id,
                chunk_index=2,
                content=new_content,
                content_hash=new_hash,
                token_count=3,
                embedding=[0.3, 0.4],
            ),
        ]

        await store.upsert_chunks(chunks)

        table_mock.upsert.assert_called_once()
        upserted_rows = table_mock.upsert.call_args.args[0]
        assert len(upserted_rows) == 1
        assert upserted_rows[0]["content_hash"] == new_hash
        assert upserted_rows[0]["embedding"] == [0.3, 0.4]

    async def test_upsert_chunks_skips_when_all_deduplicated(self) -> None:
        content = "Duplicate"
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        select_chain = _make_table_chain([{"content_hash": content_hash}])
        table_mock = MagicMock()
        table_mock.select.return_value = select_chain

        client = MagicMock()
        client.table.return_value = table_mock

        store = PgVectorStore(client)
        await store.upsert_chunks(
            [
                DocumentChunk(
                    id=uuid4(),
                    document_id=uuid4(),
                    project_id=uuid4(),
                    chunk_index=0,
                    content=content,
                    content_hash=content_hash,
                    token_count=1,
                    embedding=[0.5],
                )
            ]
        )
        table_mock.upsert.assert_not_called()

    async def test_hybrid_search_calls_rpc_and_maps_chunks(self) -> None:
        project_id = uuid4()
        doc_id = uuid4()
        chunk_id = uuid4()

        rpc_chain = MagicMock()
        rpc_chain.execute.return_value = _make_response(
            [
                {
                    "id": str(chunk_id),
                    "document_id": str(doc_id),
                    "project_id": str(project_id),
                    "chunk_index": 2,
                    "content": "PTO policy allows 20 days.",
                    "content_hash": "abc123",
                    "token_count": 6,
                    "metadata": {"source": "handbook.pdf", "page": 3},
                    "similarity": 0.91,
                    "rrf_score": 0.032,
                }
            ]
        )
        client = MagicMock()
        client.rpc.return_value = rpc_chain

        store = PgVectorStore(client)
        results = await store.hybrid_search(
            project_id=project_id,
            query_text="PTO policy",
            query_embedding=[0.1, 0.2, 0.3],
            top_k=5,
            similarity_threshold=0.35,
        )

        client.rpc.assert_called_once_with(
            "match_document_chunks_hybrid",
            {
                "p_project_id": str(project_id),
                "p_query_text": "PTO policy",
                "p_query_embedding": [0.1, 0.2, 0.3],
                "p_match_count": 5,
                "p_similarity_threshold": 0.35,
            },
        )
        assert len(results) == 1
        assert results[0].id == chunk_id
        assert results[0].similarity == 0.91
        assert results[0].rrf_score == 0.032
        assert results[0].metadata["page"] == 3


class TestSupabaseProjectRepository:
    def test_conforms_to_protocol(self) -> None:
        assert isinstance(SupabaseProjectRepository(MagicMock()), ProjectRepositoryProtocol)

    async def test_create_get_list_and_update(self) -> None:
        project_id = uuid4()
        user_id = uuid4()
        now = datetime.now(UTC)

        req_doc = RequirementsDoc(
            agent_name="HR Buddy",
            scope="Answer HR policy questions",
            target_audience="Employees",
            tone="Professional",
            must_answer_topics=["PTO"],
            must_refuse_topics=["Salaries"],
            clarifying_qa=[ClarifyingQA(question="Include contractors?", answer="No")],
            detected_tool_needs=[ToolName.CURRENT_DATE],
        )
        ground_report = GroundabilityReport(
            is_passable=True,
            critical_gaps=[
                TopicGroundability(
                    topic="PTO",
                    is_grounded=True,
                    confidence=0.95,
                    supporting_documents=["handbook.pdf"],
                )
            ],
            warnings=[],
            summary="All topics grounded.",
        )
        project = ForgeProject(
            id=project_id,
            user_id=user_id,
            title="HR Assistant",
            brief="Build an HR policy assistant.",
            status=RunStatus.RUNNING,
            requirements_doc=req_doc,
            groundability_report=ground_report,
            created_at=now,
            updated_at=now,
        )

        row = {
            "id": str(project_id),
            "user_id": str(user_id),
            "title": "HR Assistant",
            "brief": "Build an HR policy assistant.",
            "status": "running",
            "requirements_doc": {
                "agent_name": "HR Buddy",
                "scope": "Answer HR policy questions",
                "target_audience": "Employees",
                "tone": "Professional",
                "must_answer_topics": ["PTO"],
                "must_refuse_topics": ["Salaries"],
                "clarifying_qa": [{"question": "Include contractors?", "answer": "No"}],
                "detected_tool_needs": ["current_date"],
            },
            "groundability_report": {
                "is_passable": True,
                "critical_gaps": [
                    {
                        "topic": "PTO",
                        "is_grounded": True,
                        "confidence": 0.95,
                        "supporting_documents": ["handbook.pdf"],
                        "gap_reason": None,
                    }
                ],
                "warnings": [],
                "summary": "All topics grounded.",
            },
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        client = MagicMock()
        client.table.return_value = _make_table_chain([row])
        repo = SupabaseProjectRepository(client)

        created = await repo.create(project)
        assert created.id == project_id
        assert created.requirements_doc == req_doc
        assert created.groundability_report == ground_report

        fetched = await repo.get_by_id(project_id)
        assert fetched is not None
        assert fetched.status == RunStatus.RUNNING

        listed = await repo.list_by_user(user_id)
        assert len(listed) == 1

        updated = await repo.update(project)
        assert updated.title == "HR Assistant"

        client.table.return_value = _make_table_chain([])
        assert await repo.get_by_id(uuid4()) is None


class TestSupabaseDocumentRepository:
    def test_conforms_to_protocol(self) -> None:
        assert isinstance(SupabaseDocumentRepository(MagicMock()), DocumentRepositoryProtocol)

    async def test_crud_and_get_by_hash(self) -> None:
        doc_id = uuid4()
        project_id = uuid4()
        now = datetime.now(UTC)
        doc = Document(
            id=doc_id,
            project_id=project_id,
            filename="handbook.pdf",
            mime_type="application/pdf",
            storage_path=f"{project_id}/handbook.pdf",
            content_hash="deadbeef",
            metadata={"pages": 12},
            created_at=now,
        )
        row = {
            "id": str(doc_id),
            "project_id": str(project_id),
            "filename": "handbook.pdf",
            "mime_type": "application/pdf",
            "storage_path": f"{project_id}/handbook.pdf",
            "content_hash": "deadbeef",
            "metadata": {"pages": 12},
            "created_at": now.isoformat(),
        }

        client = MagicMock()
        client.table.return_value = _make_table_chain([row])
        repo = SupabaseDocumentRepository(client)

        created = await repo.create(doc)
        assert created.filename == "handbook.pdf"

        by_id = await repo.get_by_id(doc_id)
        assert by_id is not None and by_id.id == doc_id

        listed = await repo.list_by_project(project_id)
        assert len(listed) == 1

        by_hash = await repo.get_by_hash(project_id, "deadbeef")
        assert by_hash is not None and by_hash.content_hash == "deadbeef"

        client.table.return_value = _make_table_chain([])
        assert await repo.get_by_hash(project_id, "missing") is None


class TestSupabaseAgentRepository:
    def test_conforms_to_protocol(self) -> None:
        assert isinstance(SupabaseAgentRepository(MagicMock()), AgentRepositoryProtocol)

    async def test_save_get_latest_by_slug_and_list_versions(self) -> None:
        agent_id = uuid4()
        project_id = uuid4()
        now = datetime.now(UTC)
        agent = AgentDefinition(
            id=agent_id,
            project_id=project_id,
            slug="hr-assistant",
            version=2,
            system_prompt="You are an HR assistant.",
            retrieval_config=RetrievalConfig(chunk_size=500, chunk_overlap=50, top_k=4),
            selected_tools=[ToolName.CURRENT_DATE],
            output_contract=OutputContract(format="markdown", max_response_words=250),
            is_published=True,
            created_at=now,
        )
        row = {
            "id": str(agent_id),
            "project_id": str(project_id),
            "slug": "hr-assistant",
            "version": 2,
            "system_prompt": "You are an HR assistant.",
            "retrieval_config": {
                "chunk_size": 500,
                "chunk_overlap": 50,
                "top_k": 4,
                "similarity_threshold": 0.35,
                "hybrid_search": True,
            },
            "selected_tools": ["current_date"],
            "output_contract": {
                "format": "markdown",
                "require_citations": True,
                "refusal_template": "I cannot answer this based on the provided documents.",
                "max_response_words": 250,
            },
            "is_published": True,
            "created_at": now.isoformat(),
        }

        client = MagicMock()
        client.table.return_value = _make_table_chain([row])
        repo = SupabaseAgentRepository(client)

        saved = await repo.save(agent)
        assert saved.version == 2
        assert saved.selected_tools == [ToolName.CURRENT_DATE]

        latest = await repo.get_latest(project_id)
        assert latest is not None and latest.slug == "hr-assistant"

        by_slug = await repo.get_by_slug("hr-assistant")
        assert by_slug is not None and by_slug.is_published is True

        versions = await repo.list_versions(project_id)
        assert len(versions) == 1 and versions[0].retrieval_config.chunk_size == 500


class TestSupabaseEvalRepository:
    def test_conforms_to_protocol(self) -> None:
        assert isinstance(SupabaseEvalRepository(MagicMock()), EvalRepositoryProtocol)

    async def test_eval_cases_scores_iterations_and_honest_report(self) -> None:
        project_id = uuid4()
        case_id = uuid4()
        chunk_id = uuid4()

        eval_case = EvalCase(
            id=case_id,
            project_id=project_id,
            case_type=EvalCaseType.ANSWERABLE,
            question="How many PTO days?",
            expected_sources=["handbook.pdf"],
            expected_facts=["20 days"],
            should_refuse=False,
            rationale="Core policy question.",
        )
        case_row = {
            "id": str(case_id),
            "project_id": str(project_id),
            "case_type": "answerable",
            "question": "How many PTO days?",
            "expected_sources": ["handbook.pdf"],
            "expected_facts": ["20 days"],
            "should_refuse": False,
            "rationale": "Core policy question.",
        }

        score = JudgeScore(
            eval_case_id=case_id,
            grounded=True,
            correct=True,
            refusal_accurate=True,
            passed=True,
            failure_category=FailureCategory.NONE,
            reasoning="Matched expected fact.",
            deterministic_checks={"has_citation": True},
            agent_response="You get 20 days [handbook.pdf].",
            retrieved_chunk_ids=[chunk_id],
            latency_ms=120,
        )

        iter_log = IterationLog(
            iteration=1,
            score_before=0.70,
            score_after=0.90,
            failures_addressed=[case_id],
            change_type="system_prompt",
            what_changed="Clarified citation instruction.",
            why="Missing citations on 2 cases.",
        )
        iter_row = {
            "project_id": str(project_id),
            "iteration": 1,
            "score_before": 0.70,
            "score_after": 0.90,
            "failures_addressed": [str(case_id)],
            "change_type": "system_prompt",
            "what_changed": "Clarified citation instruction.",
            "why": "Missing citations on 2 cases.",
        }

        report = HonestReport(
            project_id=project_id,
            final_agent_version=2,
            per_iteration_scores=[{"iteration": 1, "pass_rate": 0.9}],
            final_pass_rate=0.9,
            remaining_failures=[],
            known_limitations=["No contractor policy uploaded."],
            recommendation="Ready for internal pilot.",
        )
        report_row = {
            "project_id": str(project_id),
            "final_agent_version": 2,
            "per_iteration_scores": [{"iteration": 1, "pass_rate": 0.9}],
            "final_pass_rate": 0.9,
            "remaining_failures": [],
            "known_limitations": ["No contractor policy uploaded."],
            "recommendation": "Ready for internal pilot.",
        }

        client = MagicMock()
        repo = SupabaseEvalRepository(client)

        client.table.return_value = _make_table_chain([case_row])
        await repo.save_eval_cases(project_id, [eval_case])
        cases = await repo.list_eval_cases(project_id)
        assert len(cases) == 1 and cases[0].case_type == EvalCaseType.ANSWERABLE

        await repo.save_judge_scores(project_id, 1, [score])

        client.table.return_value = _make_table_chain([iter_row])
        await repo.save_iteration_log(project_id, iter_log)
        logs = await repo.list_iteration_logs(project_id)
        assert len(logs) == 1 and logs[0].failures_addressed == [case_id]

        client.table.return_value = _make_table_chain([report_row])
        await repo.save_honest_report(report)
        fetched_report = await repo.get_honest_report(project_id)
        assert fetched_report is not None and fetched_report.final_pass_rate == 0.9

        client.table.return_value = _make_table_chain([])
        assert await repo.get_honest_report(uuid4()) is None


class TestSupabaseChatRepository:
    def test_conforms_to_protocol(self) -> None:
        assert isinstance(SupabaseChatRepository(MagicMock()), ChatRepositoryProtocol)

    async def test_conversation_and_messages_crud(self) -> None:
        conv_id = uuid4()
        project_id = uuid4()
        msg_id = uuid4()
        now = datetime.now(UTC)

        conv = Conversation(
            id=conv_id,
            project_id=project_id,
            agent_id=None,
            user_id=None,
            title="Builder Chat",
            created_at=now,
            updated_at=now,
        )
        conv_row = {
            "id": str(conv_id),
            "project_id": str(project_id),
            "agent_id": None,
            "user_id": None,
            "title": "Builder Chat",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        msg = Message(
            id=msg_id,
            conversation_id=conv_id,
            role="user",
            content="Build me an HR bot",
            metadata={"source": "web"},
            created_at=now,
        )
        msg_row = {
            "id": str(msg_id),
            "conversation_id": str(conv_id),
            "role": "user",
            "content": "Build me an HR bot",
            "metadata": {"source": "web"},
            "created_at": now.isoformat(),
        }

        client = MagicMock()
        repo = SupabaseChatRepository(client)

        client.table.return_value = _make_table_chain([conv_row])
        created = await repo.create_conversation(conv)
        assert created.id == conv_id
        fetched = await repo.get_conversation(conv_id)
        assert fetched is not None and fetched.title == "Builder Chat"

        client.table.return_value = _make_table_chain([msg_row])
        added = await repo.add_message(msg)
        assert added.role == "user"
        messages = await repo.list_messages(conv_id)
        assert len(messages) == 1 and messages[0].content == "Build me an HR bot"
