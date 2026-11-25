from dataclasses import dataclass

from app.domain.value_objects.enums import ToolName


@dataclass(slots=True, frozen=True)
class ClarifyingQA:
    """Single intake clarifying question and user answer."""

    question: str
    answer: str


@dataclass(slots=True, frozen=True)
class RequirementsDoc:
    """Structured requirements produced by Stage 1 (Intake Interviewer)."""

    agent_name: str
    scope: str
    target_audience: str
    tone: str
    must_answer_topics: list[str]
    must_refuse_topics: list[str]
    clarifying_qa: list[ClarifyingQA]
    detected_tool_needs: list[ToolName]

    def __post_init__(self) -> None:
        if len(self.clarifying_qa) > 5:
            raise ValueError("clarifying_qa cannot exceed 5 questions")


@dataclass(slots=True, frozen=True)
class TopicGroundability:
    """Groundability assessment for a single required topic."""

    topic: str
    is_grounded: bool
    confidence: float
    supporting_documents: list[str]
    gap_reason: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")


@dataclass(slots=True, frozen=True)
class GroundabilityReport:
    """Stage 2 Groundability Guard report verifying brief against uploaded docs."""

    is_passable: bool
    critical_gaps: list[TopicGroundability]
    warnings: list[TopicGroundability]
    summary: str

    def __post_init__(self) -> None:
        has_ungrounded_critical = any(not gap.is_grounded for gap in self.critical_gaps)
        if self.is_passable and has_ungrounded_critical:
            raise ValueError(
                "GroundabilityReport cannot be passable when ungrounded critical gaps exist"
            )
