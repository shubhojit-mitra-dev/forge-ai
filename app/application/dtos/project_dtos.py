"""Pydantic v2 DTOs for ForgeAI projects, intake, and groundability."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.value_objects.enums import ProjectStatus, ToolName


class ClarifyingQADTO(BaseModel):
    """Single intake clarifying question and user answer."""

    model_config = ConfigDict(frozen=True)

    question: Annotated[str, Field(min_length=1)]
    answer: Annotated[str, Field(min_length=1)]


class RequirementsDocDTO(BaseModel):
    """Structured requirements produced by Stage 1 (Intake Interviewer)."""

    model_config = ConfigDict(frozen=True)

    agent_name: Annotated[str, Field(min_length=3, max_length=80)]
    scope: Annotated[str, Field(min_length=10)]
    target_audience: Annotated[str, Field(min_length=3)]
    tone: Annotated[str, Field(min_length=3)]
    must_answer_topics: Annotated[list[str], Field(min_length=1)]
    must_refuse_topics: Annotated[list[str], Field(min_length=1)]
    clarifying_qa: Annotated[list[ClarifyingQADTO], Field(max_length=5)]
    detected_tool_needs: list[ToolName]


class TopicGroundabilityDTO(BaseModel):
    """Groundability assessment for a single required topic."""

    model_config = ConfigDict(frozen=True)

    topic: Annotated[str, Field(min_length=1)]
    is_grounded: bool
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    supporting_documents: list[str]
    gap_reason: str | None = None


class GroundabilityReportDTO(BaseModel):
    """Stage 2 Groundability Guard report verifying brief against uploaded docs."""

    model_config = ConfigDict(frozen=True)

    is_passable: bool
    critical_gaps: list[TopicGroundabilityDTO]
    warnings: list[TopicGroundabilityDTO]
    summary: Annotated[str, Field(min_length=1)]


class ProjectCreateDTO(BaseModel):
    """Payload to create a new ForgeAI project."""

    model_config = ConfigDict(frozen=True)

    title: Annotated[str, Field(min_length=1, max_length=120)]
    brief: Annotated[str, Field(min_length=10)]


class ProjectSummaryDTO(BaseModel):
    """Lightweight project summary for listing and status responses."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    user_id: UUID
    title: Annotated[str, Field(min_length=1, max_length=120)]
    brief: Annotated[str, Field(min_length=10)]
    status: ProjectStatus


class DocumentSummaryDTO(BaseModel):
    """Summary of an ingested document and its indexed chunks."""

    model_config = ConfigDict(frozen=True)

    document_id: UUID
    filename: Annotated[str, Field(min_length=1)]
    chunk_count: Annotated[int, Field(ge=0)]


class IntakeStartResponseDTO(BaseModel):
    """Response from Stage 1 intake question generation."""

    model_config = ConfigDict(frozen=True)

    project_id: UUID
    questions: Annotated[list[str], Field(max_length=5)]


class IntakeSubmitRequestDTO(BaseModel):
    """Request payload submitting user answers to intake questions."""

    model_config = ConfigDict(frozen=True)

    qa_pairs: Annotated[list[ClarifyingQADTO], Field(max_length=5)]


class IntakeSubmitResponseDTO(BaseModel):
    """Response combining finalized requirements and groundability report."""

    model_config = ConfigDict(frozen=True)

    requirements: RequirementsDocDTO
    groundability: GroundabilityReportDTO
