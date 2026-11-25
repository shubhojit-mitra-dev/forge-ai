"""Supabase repository implementation for evaluations, iterations, and honest reports."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

from app.domain.entities.evaluation import (
    EvalCase,
    HonestReport,
    IterationLog,
    JudgeScore,
)
from app.domain.value_objects.enums import EvalCaseType

if TYPE_CHECKING:
    from supabase import Client

type _ChangeTypeLiteral = Literal[
    "retrieval_config",
    "system_prompt",
    "output_contract",
    "tool_selection",
]


class SupabaseEvalRepository:
    """Supabase persistence adapter implementing EvalRepositoryProtocol."""

    _CASES_TABLE = "eval_cases"
    _RESULTS_TABLE = "eval_results"
    _ITERATIONS_TABLE = "iteration_logs"
    _REPORTS_TABLE = "honest_reports"

    def __init__(self, client: Client) -> None:
        self._client = client

    async def save_eval_cases(self, project_id: UUID, cases: list[EvalCase]) -> None:
        """Persist generated evaluation cases for a project."""
        if not cases:
            return
        rows = [
            {
                "id": str(case.id),
                "project_id": str(project_id),
                "case_type": case.case_type.value,
                "question": case.question,
                "expected_sources": list(case.expected_sources),
                "expected_facts": list(case.expected_facts),
                "should_refuse": case.should_refuse,
                "rationale": case.rationale,
            }
            for case in cases
        ]
        await asyncio.to_thread(
            lambda: self._client.table(self._CASES_TABLE).upsert(rows).execute()
        )

    async def list_eval_cases(self, project_id: UUID) -> list[EvalCase]:
        """List evaluation cases for a project."""
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self._CASES_TABLE)
                .select("*")
                .eq("project_id", str(project_id))
                .execute()
            )
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return [
            EvalCase(
                id=UUID(str(row["id"])),
                project_id=UUID(str(row["project_id"])),
                case_type=EvalCaseType(str(row["case_type"])),
                question=str(row["question"]),
                expected_sources=list(row.get("expected_sources", [])),
                expected_facts=list(row.get("expected_facts", [])),
                should_refuse=bool(row["should_refuse"]),
                rationale=str(row.get("rationale", "")),
            )
            for row in rows
        ]

    async def save_judge_scores(
        self,
        project_id: UUID,
        iteration: int,
        scores: list[JudgeScore],
    ) -> None:
        """Persist judge scores for a specific optimization iteration."""
        if not scores:
            return
        rows = [
            {
                "project_id": str(project_id),
                "iteration": iteration,
                "eval_case_id": str(score.eval_case_id),
                "grounded": score.grounded,
                "correct": score.correct,
                "refusal_accurate": score.refusal_accurate,
                "passed": score.passed,
                "failure_category": score.failure_category.value,
                "judge_reasoning": score.reasoning,
                "deterministic_checks": dict(score.deterministic_checks),
                "agent_response": score.agent_response,
                "retrieved_chunk_ids": [str(cid) for cid in score.retrieved_chunk_ids],
                "latency_ms": score.latency_ms,
            }
            for score in scores
        ]
        await asyncio.to_thread(
            lambda: self._client.table(self._RESULTS_TABLE).insert(rows).execute()
        )

    async def save_iteration_log(self, project_id: UUID, log: IterationLog) -> None:
        """Persist a single critic-optimizer iteration log."""
        row = {
            "project_id": str(project_id),
            "iteration": log.iteration,
            "score_before": log.score_before,
            "score_after": log.score_after,
            "failures_addressed": [str(fid) for fid in log.failures_addressed],
            "change_type": log.change_type,
            "what_changed": log.what_changed,
            "why": log.why,
        }
        await asyncio.to_thread(
            lambda: self._client.table(self._ITERATIONS_TABLE).insert(row).execute()
        )

    async def list_iteration_logs(self, project_id: UUID) -> list[IterationLog]:
        """List all critic-optimizer iteration logs for a project."""
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self._ITERATIONS_TABLE)
                .select("*")
                .eq("project_id", str(project_id))
                .order("iteration", desc=False)
                .execute()
            )
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return [
            IterationLog(
                iteration=int(row["iteration"]),
                score_before=float(row["score_before"]),
                score_after=float(row["score_after"]),
                failures_addressed=[UUID(str(fid)) for fid in row.get("failures_addressed", [])],
                change_type=cast("_ChangeTypeLiteral", str(row["change_type"])),
                what_changed=str(row["what_changed"]),
                why=str(row["why"]),
            )
            for row in rows
        ]

    async def save_honest_report(self, report: HonestReport) -> None:
        """Persist the final honest report for a project."""
        row = {
            "project_id": str(report.project_id),
            "final_agent_version": report.final_agent_version,
            "per_iteration_scores": list(report.per_iteration_scores),
            "final_pass_rate": report.final_pass_rate,
            "remaining_failures": list(report.remaining_failures),
            "known_limitations": list(report.known_limitations),
            "recommendation": report.recommendation,
        }
        await asyncio.to_thread(
            lambda: self._client.table(self._REPORTS_TABLE).upsert(row).execute()
        )

    async def get_honest_report(self, project_id: UUID) -> HonestReport | None:
        """Fetch the final honest report for a project if available."""
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self._REPORTS_TABLE)
                .select("*")
                .eq("project_id", str(project_id))
                .limit(1)
                .execute()
            )
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        if not rows:
            return None
        row = rows[0]
        return HonestReport(
            project_id=UUID(str(row["project_id"])),
            final_agent_version=int(row["final_agent_version"]),
            per_iteration_scores=list(row.get("per_iteration_scores", [])),
            final_pass_rate=float(row["final_pass_rate"]),
            remaining_failures=list(row.get("remaining_failures", [])),
            known_limitations=list(row.get("known_limitations", [])),
            recommendation=str(row["recommendation"]),
        )
