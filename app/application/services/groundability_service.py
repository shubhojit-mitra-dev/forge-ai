"""Stage 2 Groundability Guard service: verifies must_answer topics against chunks."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from app.application.prompts.groundability_prompts import build_groundability_messages
from app.domain.entities.requirements import (
    GroundabilityReport,
    RequirementsDoc,
    TopicGroundability,
)
from app.domain.exceptions import ValidationDomainError

if TYPE_CHECKING:
    from uuid import UUID

    from app.domain.protocols.llm_gateway import EmbeddingGatewayProtocol, LLMGatewayProtocol
    from app.domain.protocols.vector_store import VectorStoreProtocol

DEFAULT_CONFIDENCE_THRESHOLD = 0.45
DEFAULT_WARNING_THRESHOLD = 0.70


def _parse_json_object(raw_content: str) -> dict[str, Any]:
    """Strip optional markdown code fences and decode a JSON object."""
    cleaned = raw_content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValidationDomainError(
            "INVALID_LLM_JSON",
            f"Groundability LLM returned invalid JSON: {exc}",
        ) from exc

    if not isinstance(parsed, dict):
        raise ValidationDomainError(
            "INVALID_LLM_JSON",
            "Expected a JSON object from Groundability LLM.",
        )
    return parsed


class GroundabilityService:
    """Evaluates whether uploaded document chunks support every must_answer topic."""

    def __init__(
        self,
        embedding_gateway: EmbeddingGatewayProtocol,
        vector_store: VectorStoreProtocol,
        llm_gateway: LLMGatewayProtocol,
        tier: str = "fast-worker",
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        top_k: int = 5,
    ) -> None:
        self._embedding_gateway = embedding_gateway
        self._vector_store = vector_store
        self._llm_gateway = llm_gateway
        self._tier = tier
        self._confidence_threshold = confidence_threshold
        self._top_k = top_k

    async def evaluate(
        self,
        project_id: UUID,
        requirements: RequirementsDoc,
    ) -> GroundabilityReport:
        """Assess every must_answer_topic and block if any is ungrounded or low-confidence."""
        critical_gaps: list[TopicGroundability] = []
        warnings: list[TopicGroundability] = []

        for topic in requirements.must_answer_topics:
            assessment = await self._assess_topic(project_id=project_id, topic=topic)
            if not assessment.is_grounded or assessment.confidence < self._confidence_threshold:
                gap_reason = assessment.gap_reason or (
                    f"Confidence {assessment.confidence:.2f} is below required threshold "
                    f"{self._confidence_threshold:.2f}."
                )
                critical_gaps.append(
                    TopicGroundability(
                        topic=assessment.topic,
                        is_grounded=assessment.is_grounded,
                        confidence=assessment.confidence,
                        supporting_documents=assessment.supporting_documents,
                        gap_reason=gap_reason,
                    )
                )
            elif assessment.confidence < DEFAULT_WARNING_THRESHOLD:
                warnings.append(assessment)

        is_passable = len(critical_gaps) == 0
        total_topics = len(requirements.must_answer_topics)
        if is_passable:
            summary = f"All {total_topics} required topics are grounded in the uploaded documents."
        else:
            summary = (
                f"Groundability check failed: {len(critical_gaps)} of {total_topics} "
                "required topics lack sufficient document support."
            )

        return GroundabilityReport(
            is_passable=is_passable,
            critical_gaps=critical_gaps,
            warnings=warnings,
            summary=summary,
        )

    async def _assess_topic(self, project_id: UUID, topic: str) -> TopicGroundability:
        embeddings = await self._embedding_gateway.embed_texts([topic])
        if not embeddings:
            return TopicGroundability(
                topic=topic,
                is_grounded=False,
                confidence=0.0,
                supporting_documents=[],
                gap_reason="Failed to generate embedding for topic.",
            )

        chunks = await self._vector_store.hybrid_search(
            project_id=project_id,
            query_text=topic,
            query_embedding=embeddings[0],
            top_k=self._top_k,
        )
        if not chunks:
            return TopicGroundability(
                topic=topic,
                is_grounded=False,
                confidence=0.0,
                supporting_documents=[],
                gap_reason="No relevant document chunks found for this topic.",
            )

        messages = build_groundability_messages(topic=topic, chunks=chunks)
        response = await self._llm_gateway.complete(
            messages=messages,
            tier=self._tier,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        payload = _parse_json_object(response.content)

        confidence = float(payload.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
        is_grounded = bool(payload.get("is_grounded", False))
        supporting_docs = [str(doc) for doc in payload.get("supporting_documents", [])]
        raw_gap = payload.get("gap_reason")
        gap_reason = str(raw_gap).strip() if raw_gap else None

        return TopicGroundability(
            topic=topic,
            is_grounded=is_grounded,
            confidence=confidence,
            supporting_documents=supporting_docs,
            gap_reason=gap_reason,
        )
