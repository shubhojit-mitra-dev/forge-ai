"""Forge pipeline execution, SSE streaming, and artifact export routes."""

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sse_starlette import EventSourceResponse

from app.application.dtos.agent_dtos import AgentDefinitionDTO
from app.application.dtos.eval_dtos import EvalCaseDTO, HonestReportDTO, IterationLogDTO
from app.application.dtos.project_dtos import GroundabilityReportDTO, RequirementsDocDTO
from app.domain.entities.evaluation import HonestReport
from app.domain.exceptions import GroundabilityBlockedError
from app.presentation.dependencies import (
    AgentRepoDep,
    CurrentUserDep,
    EvalRepoDep,
    PipelineOrchestratorDep,
    ProjectRepoDep,
)
from app.presentation.routes._mappers import (
    require_owned_project,
    to_agent_dto,
    to_eval_case_dto,
    to_groundability_dto,
    to_honest_report_dto,
    to_iteration_log_dto,
    to_requirements_dto,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["forge"])


class ProjectArtifactsDTO(BaseModel):
    """Exportable JSON + Markdown artifacts for a forged project."""

    model_config = ConfigDict(frozen=True)

    project_id: UUID
    requirements: RequirementsDocDTO | None = None
    groundability: GroundabilityReportDTO | None = None
    agent_definition: AgentDefinitionDTO | None = None
    eval_cases: list[EvalCaseDTO]
    iterations: list[IterationLogDTO]
    honest_report: HonestReportDTO | None = None
    honest_report_markdown: str | None = None


@router.post("/forge/run", response_model=HonestReportDTO)
async def run_forge_pipeline(
    project_id: UUID,
    current_user: CurrentUserDep,
    project_repo: ProjectRepoDep,
    orchestrator: PipelineOrchestratorDep,
) -> HonestReportDTO:
    """Trigger the unattended ForgeAI pipeline (Stages 3-7)."""
    project = await require_owned_project(project_repo, project_id, current_user.user_id)
    if project.groundability_report is not None and not project.groundability_report.is_passable:
        raise GroundabilityBlockedError(
            "GROUNDABILITY_BLOCKED",
            project.groundability_report.summary,
        )

    report = await orchestrator.run(project_id=project_id)
    return to_honest_report_dto(report)


@router.get("/forge/stream")
async def stream_forge_pipeline(
    project_id: UUID,
    current_user: CurrentUserDep,
    project_repo: ProjectRepoDep,
    orchestrator: PipelineOrchestratorDep,
) -> EventSourceResponse:
    """Stream live ForgeAI pipeline events over Server-Sent Events (SSE)."""
    project = await require_owned_project(project_repo, project_id, current_user.user_id)
    if project.groundability_report is not None and not project.groundability_report.is_passable:
        raise GroundabilityBlockedError(
            "GROUNDABILITY_BLOCKED",
            project.groundability_report.summary,
        )

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def on_event(payload: dict[str, Any]) -> None:
            await queue.put(payload)

        async def _runner() -> None:
            try:
                await orchestrator.run(project_id=project_id, on_event=on_event)
            except Exception as exc:
                await queue.put({"event": "error", "detail": str(exc)})
            finally:
                await queue.put(None)

        task = asyncio.create_task(_runner())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event_name = str(item.get("event", "message"))
                yield {"event": event_name, "data": json.dumps(item)}
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    return EventSourceResponse(event_generator())


def _render_honest_report_markdown(report: HonestReport) -> str:
    """Render an HonestReport as a transparent Markdown summary."""
    lines = [
        "# ForgeAI Honest Report",
        "",
        f"- **Project ID:** `{report.project_id}`",
        f"- **Final Agent Version:** v{report.final_agent_version}",
        f"- **Final Pass Rate:** {report.final_pass_rate:.1%}",
        f"- **Recommendation:** {report.recommendation}",
    ]
    if report.known_limitations:
        lines.extend(["", "## Known Limitations"])
        lines.extend(f"- {item}" for item in report.known_limitations)
    if report.remaining_failures:
        lines.extend(["", "## Remaining Failures"])
        for failure in report.remaining_failures:
            lines.append(
                f"- `{failure.get('eval_case_id', '')}` "
                f"[{failure.get('failure_category', 'unknown')}]: "
                f"{failure.get('reasoning', '')}"
            )
    return "\n".join(lines)


@router.get("/artifacts", response_model=ProjectArtifactsDTO)
async def get_project_artifacts(
    project_id: UUID,
    current_user: CurrentUserDep,
    project_repo: ProjectRepoDep,
    agent_repo: AgentRepoDep,
    eval_repo: EvalRepoDep,
) -> ProjectArtifactsDTO:
    """Export all JSON and Markdown artifacts for a forged project."""
    project = await require_owned_project(project_repo, project_id, current_user.user_id)
    latest_agent = await agent_repo.get_latest(project_id)
    eval_cases = await eval_repo.list_eval_cases(project_id)
    iterations = await eval_repo.list_iteration_logs(project_id)
    honest_report = await eval_repo.get_honest_report(project_id)

    markdown = _render_honest_report_markdown(honest_report) if honest_report is not None else None

    return ProjectArtifactsDTO(
        project_id=project_id,
        requirements=(
            to_requirements_dto(project.requirements_doc)
            if project.requirements_doc is not None
            else None
        ),
        groundability=(
            to_groundability_dto(project.groundability_report)
            if project.groundability_report is not None
            else None
        ),
        agent_definition=to_agent_dto(latest_agent) if latest_agent is not None else None,
        eval_cases=[to_eval_case_dto(case) for case in eval_cases],
        iterations=[to_iteration_log_dto(log) for log in iterations],
        honest_report=to_honest_report_dto(honest_report) if honest_report is not None else None,
        honest_report_markdown=markdown,
    )
