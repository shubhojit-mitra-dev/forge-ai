from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.entities.document import Document, DocumentChunk
from app.domain.entities.project import ForgeProject
from app.domain.entities.requirements import (
    ClarifyingQA,
    GroundabilityReport,
    RequirementsDoc,
    TopicGroundability,
)
from app.domain.value_objects.enums import RunStatus, ToolName


@pytest.mark.unit
def test_document_and_chunk_creation() -> None:
    now = datetime.now(UTC)
    project_id = uuid4()
    doc_id = uuid4()
    doc = Document(
        id=doc_id,
        project_id=project_id,
        filename="policy.pdf",
        mime_type="application/pdf",
        storage_path="projects/123/policy.pdf",
        content_hash="abc123",
        metadata={"pages": 4},
        created_at=now,
    )
    assert doc.id == doc_id
    assert doc.project_id == project_id
    assert doc.filename == "policy.pdf"
    assert doc.metadata == {"pages": 4}
    assert doc.created_at == now

    chunk = DocumentChunk(
        id=uuid4(),
        document_id=doc_id,
        project_id=project_id,
        chunk_index=0,
        content="Employees receive 20 days of PTO.",
        content_hash="chunkhash",
        token_count=7,
        embedding=None,
        metadata={"page": 1},
    )
    assert chunk.similarity == 0.0
    assert chunk.rrf_score == 0.0
    assert chunk.embedding is None


@pytest.mark.unit
def test_clarifying_qa_is_frozen() -> None:
    qa = ClarifyingQA(question="Who is the audience?", answer="New hires")
    with pytest.raises(FrozenInstanceError):
        qa.answer = "Executives"  # type: ignore[misc]


@pytest.mark.unit
def test_requirements_doc_enforces_max_five_clarifying_qa() -> None:
    five_qas = [ClarifyingQA(question=f"Q{i}", answer=f"A{i}") for i in range(5)]
    req = RequirementsDoc(
        agent_name="HR Policy Assistant",
        scope="Answer employee handbook questions accurately.",
        target_audience="All full-time employees",
        tone="Professional and helpful",
        must_answer_topics=["PTO policy", "Expense reimbursement"],
        must_refuse_topics=["Personal salary negotiations"],
        clarifying_qa=five_qas,
        detected_tool_needs=[ToolName.CURRENT_DATE],
    )
    assert len(req.clarifying_qa) == 5

    six_qas = [ClarifyingQA(question=f"Q{i}", answer=f"A{i}") for i in range(6)]
    with pytest.raises(ValueError, match="5"):
        RequirementsDoc(
            agent_name="HR Policy Assistant",
            scope="Answer employee handbook questions accurately.",
            target_audience="All full-time employees",
            tone="Professional and helpful",
            must_answer_topics=["PTO policy"],
            must_refuse_topics=["Salary"],
            clarifying_qa=six_qas,
            detected_tool_needs=[],
        )


@pytest.mark.unit
def test_groundability_report_is_passable_invariant() -> None:
    ungrounded = TopicGroundability(
        topic="401k matching",
        is_grounded=False,
        confidence=0.1,
        supporting_documents=[],
        gap_reason="No retirement benefits document uploaded.",
    )
    grounded = TopicGroundability(
        topic="PTO policy",
        is_grounded=True,
        confidence=0.95,
        supporting_documents=["policy.pdf"],
    )

    with pytest.raises(ValueError, match="passable"):
        GroundabilityReport(
            is_passable=True,
            critical_gaps=[ungrounded],
            warnings=[],
            summary="Missing 401k docs.",
        )

    blocked_report = GroundabilityReport(
        is_passable=False,
        critical_gaps=[ungrounded],
        warnings=[],
        summary="Missing 401k docs.",
    )
    assert blocked_report.is_passable is False

    passing_report = GroundabilityReport(
        is_passable=True,
        critical_gaps=[],
        warnings=[grounded],
        summary="All must-answer topics grounded.",
    )
    assert passing_report.is_passable is True


@pytest.mark.unit
def test_forge_project_lifecycle_fields() -> None:
    status = next(iter(RunStatus))
    project = ForgeProject(
        id=uuid4(),
        user_id=uuid4(),
        title="HR Bot",
        brief="Build an HR policy assistant.",
        status=status,
    )
    assert project.requirements_doc is None
    assert project.groundability_report is None
    assert project.status == status
