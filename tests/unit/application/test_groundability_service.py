"""Unit tests for GroundabilityService (Stage 2: Groundability Guard)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.services.groundability_service import GroundabilityService
from app.domain.entities.document import DocumentChunk
from app.domain.entities.requirements import (
    GroundabilityReport,
    RequirementsDoc,
)
from app.domain.protocols.llm_gateway import LLMResponse


def _make_requirements(topics: list[str]) -> RequirementsDoc:
    return RequirementsDoc(
        agent_name="HR Policy Assistant",
        scope="Answer employee questions strictly from the HR handbook.",
        target_audience="Full-time employees",
        tone="Professional and empathetic",
        must_answer_topics=topics,
        must_refuse_topics=["Legal advice"],
        clarifying_qa=[],
        detected_tool_needs=[],
    )


def _make_chunk(project_id_str: str, filename: str, content: str) -> DocumentChunk:
    return DocumentChunk(
        id=uuid4(),
        document_id=uuid4(),
        project_id=uuid4(),
        chunk_index=0,
        content=content,
        content_hash="hash123",
        token_count=20,
        metadata={"filename": filename, "project": project_id_str},
    )


@pytest.mark.unit
async def test_groundability_passes_when_all_topics_grounded_above_threshold() -> None:
    project_id = uuid4()
    embedding_gateway = AsyncMock()
    embedding_gateway.embed_texts.return_value = [[0.5, 0.5]]

    vector_store = AsyncMock()
    vector_store.hybrid_search.return_value = [
        _make_chunk(str(project_id), "handbook.pdf", "Employees get 20 days PTO annually.")
    ]

    llm_gateway = AsyncMock()
    llm_gateway.complete.return_value = LLMResponse(
        content=json.dumps(
            {
                "is_grounded": True,
                "confidence": 0.92,
                "supporting_documents": ["handbook.pdf"],
                "gap_reason": None,
            }
        ),
        model="gemini-2.5-flash-lite",
        prompt_tokens=80,
        completion_tokens=30,
        latency_ms=10,
    )

    service = GroundabilityService(
        embedding_gateway=embedding_gateway,
        vector_store=vector_store,
        llm_gateway=llm_gateway,
    )

    report = await service.evaluate(
        project_id=project_id,
        requirements=_make_requirements(["Annual PTO allowance"]),
    )

    assert isinstance(report, GroundabilityReport)
    assert report.is_passable is True
    assert report.critical_gaps == []
    assert report.warnings == []


@pytest.mark.unit
async def test_groundability_blocks_when_topic_is_ungrounded() -> None:
    project_id = uuid4()
    embedding_gateway = AsyncMock()
    embedding_gateway.embed_texts.return_value = [[0.1, 0.2]]

    vector_store = AsyncMock()
    vector_store.hybrid_search.return_value = [
        _make_chunk(str(project_id), "handbook.pdf", "Office hours are 9am to 5pm.")
    ]

    llm_gateway = AsyncMock()
    llm_gateway.complete.return_value = LLMResponse(
        content=json.dumps(
            {
                "is_grounded": False,
                "confidence": 0.15,
                "supporting_documents": [],
                "gap_reason": "No salary band or compensation table exists in the documents.",
            }
        ),
        model="gemini-2.5-flash-lite",
        prompt_tokens=80,
        completion_tokens=30,
        latency_ms=10,
    )

    service = GroundabilityService(
        embedding_gateway=embedding_gateway,
        vector_store=vector_store,
        llm_gateway=llm_gateway,
    )

    report = await service.evaluate(
        project_id=project_id,
        requirements=_make_requirements(["Executive salary bands"]),
    )

    assert report.is_passable is False
    assert len(report.critical_gaps) == 1
    assert report.critical_gaps[0].topic == "Executive salary bands"
    assert (
        report.critical_gaps[0].gap_reason
        == "No salary band or compensation table exists in the documents."
    )


@pytest.mark.unit
async def test_groundability_blocks_when_confidence_below_threshold() -> None:
    project_id = uuid4()
    embedding_gateway = AsyncMock()
    embedding_gateway.embed_texts.return_value = [[0.1, 0.2]]

    vector_store = AsyncMock()
    vector_store.hybrid_search.return_value = [
        _make_chunk(str(project_id), "handbook.pdf", "Parental leave is mentioned briefly.")
    ]

    llm_gateway = AsyncMock()
    llm_gateway.complete.return_value = LLMResponse(
        content=json.dumps(
            {
                "is_grounded": True,
                "confidence": 0.40,
                "supporting_documents": ["handbook.pdf"],
                "gap_reason": "Only mentions parental leave without duration details.",
            }
        ),
        model="gemini-2.5-flash-lite",
        prompt_tokens=80,
        completion_tokens=30,
        latency_ms=10,
    )

    service = GroundabilityService(
        embedding_gateway=embedding_gateway,
        vector_store=vector_store,
        llm_gateway=llm_gateway,
    )

    report = await service.evaluate(
        project_id=project_id,
        requirements=_make_requirements(["Parental leave duration"]),
    )

    assert report.is_passable is False
    assert len(report.critical_gaps) == 1
    assert report.critical_gaps[0].confidence == 0.40


@pytest.mark.unit
async def test_groundability_blocks_without_llm_call_when_no_chunks_found() -> None:
    project_id = uuid4()
    embedding_gateway = AsyncMock()
    embedding_gateway.embed_texts.return_value = [[0.1, 0.2]]

    vector_store = AsyncMock()
    vector_store.hybrid_search.return_value = []

    llm_gateway = AsyncMock()

    service = GroundabilityService(
        embedding_gateway=embedding_gateway,
        vector_store=vector_store,
        llm_gateway=llm_gateway,
    )

    report = await service.evaluate(
        project_id=project_id,
        requirements=_make_requirements(["Stock option vesting schedule"]),
    )

    assert report.is_passable is False
    assert len(report.critical_gaps) == 1
    assert report.critical_gaps[0].is_grounded is False
    assert report.critical_gaps[0].confidence == 0.0
    assert report.critical_gaps[0].gap_reason is not None
    llm_gateway.complete.assert_not_awaited()
