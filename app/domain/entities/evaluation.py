from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from app.domain.value_objects.enums import EvalCaseType, FailureCategory, RunStatus


@dataclass(slots=True)
class EvalCase:
    """Single generated evaluation case (answerable, refusal, or edge)."""

    id: UUID
    project_id: UUID
    case_type: EvalCaseType
    question: str
    expected_sources: list[str]
    expected_facts: list[str]
    should_refuse: bool
    rationale: str


@dataclass(slots=True)
class JudgeScore:
    """Evaluation verdict produced by deterministic checks and LLM judge."""

    eval_case_id: UUID
    grounded: bool
    correct: bool
    refusal_accurate: bool
    passed: bool
    failure_category: FailureCategory
    reasoning: str
    deterministic_checks: dict[str, bool] = field(default_factory=dict)
    agent_response: str = ""
    retrieved_chunk_ids: list[UUID] = field(default_factory=list)
    latency_ms: int = 0


@dataclass(slots=True)
class EvalRun:
    """Aggregated evaluation run for a specific agent version and iteration."""

    id: UUID
    project_id: UUID
    agent_version: int
    iteration: int
    overall_score: float
    pass_rate: float
    status: RunStatus
    metrics: dict[str, float | int] = field(default_factory=dict)
    scores: list[JudgeScore] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class IterationLog:
    """Record of a single Critic-Optimizer improvement iteration (1..3)."""

    iteration: int
    score_before: float
    score_after: float
    failures_addressed: list[UUID]
    change_type: Literal["retrieval_config", "system_prompt", "output_contract", "tool_selection"]
    what_changed: str
    why: str

    def __post_init__(self) -> None:
        if not 1 <= self.iteration <= 3:
            raise ValueError("iteration must be between 1 and 3")
        if not 0.0 <= self.score_before <= 1.0:
            raise ValueError("score_before must be between 0.0 and 1.0")
        if not 0.0 <= self.score_after <= 1.0:
            raise ValueError("score_after must be between 0.0 and 1.0")


@dataclass(slots=True)
class HonestReport:
    """Transparent final factory report detailing pass rates and remaining failures."""

    project_id: UUID
    final_agent_version: int
    per_iteration_scores: list[dict[str, float | int]]
    final_pass_rate: float
    remaining_failures: list[dict[str, str]]
    known_limitations: list[str]
    recommendation: str
