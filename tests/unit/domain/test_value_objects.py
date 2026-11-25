from dataclasses import FrozenInstanceError
from uuid import UUID, uuid4

import pytest

from app.domain.value_objects import (
    AgentId,
    ChangeType,
    ChunkId,
    ConversationId,
    DocumentId,
    EvalCaseId,
    EvalCaseType,
    EvalRunId,
    FailureCategory,
    MessageRole,
    ProjectId,
    ProjectStatus,
    RunStatus,
    ScoreBreakdown,
    ToolName,
    UserId,
)


@pytest.mark.unit
class TestIds:
    def test_newtype_ids_wrap_uuid(self) -> None:
        raw: UUID = uuid4()
        ids = [
            ProjectId(raw),
            DocumentId(raw),
            ChunkId(raw),
            AgentId(raw),
            EvalCaseId(raw),
            EvalRunId(raw),
            ConversationId(raw),
            UserId(raw),
        ]
        for typed_id in ids:
            assert typed_id == raw
            assert isinstance(typed_id, UUID)


@pytest.mark.unit
class TestEnums:
    def test_project_status_values(self) -> None:
        assert {s.value for s in ProjectStatus} == {
            "drafting",
            "intake",
            "blocked",
            "forging",
            "ready",
            "failed",
        }
        assert ProjectStatus.DRAFTING == "drafting"

    def test_eval_case_type_values(self) -> None:
        assert {e.value for e in EvalCaseType} == {"answerable", "refusal", "edge"}
        assert EvalCaseType.ANSWERABLE == "answerable"

    def test_failure_category_values(self) -> None:
        assert {f.value for f in FailureCategory} == {
            "none",
            "retrieval_miss",
            "prompt_defect",
            "hallucination",
            "wrong_refusal",
        }

    def test_tool_name_values(self) -> None:
        assert {t.value for t in ToolName} == {
            "csv_lookup",
            "calculator",
            "weather_http",
            "current_date",
        }

    def test_run_status_values(self) -> None:
        assert {r.value for r in RunStatus} == {
            "pending",
            "running",
            "completed",
            "failed",
            "stopped_early",
        }

    def test_message_role_values(self) -> None:
        assert {m.value for m in MessageRole} == {"user", "assistant", "system"}

    def test_change_type_values(self) -> None:
        assert {c.value for c in ChangeType} == {
            "retrieval_config",
            "system_prompt",
            "output_contract",
            "tool_selection",
        }


@pytest.mark.unit
class TestScoreBreakdown:
    def test_frozen_and_slots(self) -> None:
        score = ScoreBreakdown(
            total_cases=10,
            passed_cases=8,
            grounded_count=9,
            correct_count=7,
            refusal_accurate_count=10,
        )
        assert not hasattr(score, "__dict__")
        with pytest.raises(FrozenInstanceError):
            score.passed_cases = 9  # type: ignore[misc]

    def test_rates_calculation(self) -> None:
        score = ScoreBreakdown(
            total_cases=10,
            passed_cases=8,
            grounded_count=9,
            correct_count=7,
            refusal_accurate_count=10,
        )
        assert score.pass_rate == pytest.approx(0.8)
        assert score.grounded_rate == pytest.approx(0.9)
        assert score.correct_rate == pytest.approx(0.7)
        assert score.refusal_accuracy == pytest.approx(1.0)

    def test_rates_return_zero_when_total_cases_is_zero(self) -> None:
        score = ScoreBreakdown(
            total_cases=0,
            passed_cases=0,
            grounded_count=0,
            correct_count=0,
            refusal_accurate_count=0,
        )
        assert score.pass_rate == 0.0
        assert score.grounded_rate == 0.0
        assert score.correct_rate == 0.0
        assert score.refusal_accuracy == 0.0
