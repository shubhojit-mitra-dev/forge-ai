"""Stage 7 Honest Reporter Service compiling transparent evaluation reports."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from app.domain.entities.evaluation import HonestReport

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from app.domain.entities.agent_definition import AgentDefinition
    from app.domain.entities.evaluation import EvalCase, IterationLog, JudgeScore


class ReporterService:
    """Compiles transparent HonestReport artifacts without inflating or hiding failures."""

    def compile_report(
        self,
        *,
        project_id: UUID,
        final_agent: AgentDefinition,
        iteration_logs: Sequence[IterationLog],
        final_scores: Sequence[JudgeScore],
        eval_cases: Sequence[EvalCase],
        stop_reason: str = "",
    ) -> HonestReport:
        """Build an HonestReport from optimization logs and final judge scores."""
        total_cases = len(final_scores)
        passed_cases = sum(1 for score in final_scores if score.passed)
        final_pass_rate = (passed_cases / total_cases) if total_cases > 0 else 0.0

        per_iteration_scores: list[dict[str, float | int]] = [
            {
                "iteration": log.iteration,
                "score_before": round(log.score_before, 4),
                "score_after": round(log.score_after, 4),
                "delta": round(log.score_after - log.score_before, 4),
                "failures_addressed": len(log.failures_addressed),
            }
            for log in iteration_logs
        ]

        cases_by_id = {case.id: case for case in eval_cases}
        remaining_failures: list[dict[str, str]] = []
        failure_counts: Counter[str] = Counter()

        for score in final_scores:
            if score.passed:
                continue
            category = score.failure_category.value
            failure_counts[category] += 1
            case = cases_by_id.get(score.eval_case_id)
            remaining_failures.append(
                {
                    "eval_case_id": str(score.eval_case_id),
                    "question": case.question if case is not None else "",
                    "failure_category": category,
                    "reasoning": score.reasoning,
                }
            )

        known_limitations = self._build_known_limitations(
            failure_counts=failure_counts,
            stop_reason=stop_reason,
            total_cases=total_cases,
        )
        recommendation = self._build_recommendation(
            final_pass_rate=final_pass_rate,
            remaining_failure_count=len(remaining_failures),
        )

        return HonestReport(
            project_id=project_id,
            final_agent_version=final_agent.version,
            per_iteration_scores=per_iteration_scores,
            final_pass_rate=final_pass_rate,
            remaining_failures=remaining_failures,
            known_limitations=known_limitations,
            recommendation=recommendation,
        )

    @staticmethod
    def _build_known_limitations(
        *,
        failure_counts: Counter[str],
        stop_reason: str,
        total_cases: int,
    ) -> list[str]:
        limitations: list[str] = []
        if total_cases == 0:
            limitations.append("No evaluation cases were executed.")
        for category, count in sorted(failure_counts.items()):
            limitations.append(
                f"{count} evaluation case(s) remain failing under category '{category}'."
            )
        if stop_reason == "diminishing_returns":
            limitations.append(
                "Optimization stopped early due to diminishing returns (< 2% improvement)."
            )
        elif stop_reason == "budget_cap_reached":
            limitations.append("Optimization stopped early due to LLM call budget cap.")
        elif stop_reason == "max_iterations_reached" and failure_counts:
            limitations.append(
                "Optimization reached the maximum 3-iteration bound with remaining failures."
            )
        return limitations

    @staticmethod
    def _build_recommendation(
        *,
        final_pass_rate: float,
        remaining_failure_count: int,
    ) -> str:
        if final_pass_rate >= 0.90 and remaining_failure_count == 0:
            return "Ready for deployment: all evaluation cases passed."
        if final_pass_rate >= 0.90:
            return (
                f"Ready for supervised deployment ({final_pass_rate:.0%} pass rate; "
                f"{remaining_failure_count} remaining failure(s) documented)."
            )
        if final_pass_rate >= 0.70:
            return (
                f"Deploy with caution ({final_pass_rate:.0%} pass rate): "
                "review remaining failures and consider adding clearer source documents."
            )
        return (
            f"Not ready for unattended deployment ({final_pass_rate:.0%} pass rate): "
            "expand source documentation or narrow agent scope before retrying."
        )
