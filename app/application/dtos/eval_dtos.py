"""Pydantic v2 DTOs for ForgeAI evaluations, judge scores, iterations, and reports."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.value_objects.enums import EvalCaseType, FailureCategory


class EvalCaseDTO(BaseModel):
    """Single generated evaluation case (answerable, refusal, or edge)."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    case_type: EvalCaseType
    question: Annotated[str, Field(min_length=1)]
    expected_sources: list[str]
    expected_facts: list[str]
    should_refuse: bool
    rationale: Annotated[str, Field(min_length=1)]


class JudgeScoreDTO(BaseModel):
    """Evaluation verdict produced by deterministic checks and LLM judge."""

    model_config = ConfigDict(frozen=True)

    eval_case_id: UUID
    grounded: bool
    correct: bool
    refusal_accurate: bool
    passed: bool
    failure_category: FailureCategory
    reasoning: Annotated[str, Field(min_length=1)]
    deterministic_checks: dict[str, bool]


class IterationLogDTO(BaseModel):
    """Record of a single Critic-Optimizer improvement iteration (1..3)."""

    model_config = ConfigDict(frozen=True)

    iteration: Annotated[int, Field(ge=1, le=3)]
    score_before: Annotated[float, Field(ge=0.0, le=1.0)]
    score_after: Annotated[float, Field(ge=0.0, le=1.0)]
    failures_addressed: list[UUID]
    change_type: Literal[
        "retrieval_config",
        "system_prompt",
        "output_contract",
        "tool_selection",
    ]
    what_changed: Annotated[str, Field(min_length=1)]
    why: Annotated[str, Field(min_length=1)]


class HonestReportDTO(BaseModel):
    """Transparent final factory report detailing pass rates and remaining failures."""

    model_config = ConfigDict(frozen=True)

    project_id: UUID
    final_agent_version: Annotated[int, Field(ge=1)]
    per_iteration_scores: list[dict[str, float | int]]
    final_pass_rate: Annotated[float, Field(ge=0.0, le=1.0)]
    remaining_failures: list[dict[str, str]]
    known_limitations: list[str]
    recommendation: Annotated[str, Field(min_length=1)]
