"""Project management routes."""

from uuid import UUID, uuid4

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from app.application.dtos.agent_dtos import AgentDefinitionDTO
from app.application.dtos.eval_dtos import HonestReportDTO, IterationLogDTO
from app.application.dtos.project_dtos import (
    DocumentSummaryDTO,
    GroundabilityReportDTO,
    ProjectCreateDTO,
    ProjectSummaryDTO,
    RequirementsDocDTO,
)
from app.domain.entities.project import ForgeProject
from app.domain.value_objects.enums import RunStatus
from app.presentation.dependencies import (
    AgentRepoDep,
    CurrentUserDep,
    DocumentRepoDep,
    EvalRepoDep,
    ProjectRepoDep,
)
from app.presentation.routes._mappers import (
    require_owned_project,
    to_agent_dto,
    to_groundability_dto,
    to_honest_report_dto,
    to_iteration_log_dto,
    to_project_summary_dto,
    to_requirements_dto,
)

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectDetailDTO(BaseModel):
    """Full project state, artifacts, and evaluation summary."""

    model_config = ConfigDict(frozen=True)

    project: ProjectSummaryDTO
    documents: list[DocumentSummaryDTO]
    requirements: RequirementsDocDTO | None = None
    groundability: GroundabilityReportDTO | None = None
    latest_agent: AgentDefinitionDTO | None = None
    honest_report: HonestReportDTO | None = None
    iterations: list[IterationLogDTO]


@router.post("", response_model=ProjectSummaryDTO, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreateDTO,
    current_user: CurrentUserDep,
    project_repo: ProjectRepoDep,
) -> ProjectSummaryDTO:
    """Create a new ForgeAI project from an initial brief."""
    project = ForgeProject(
        id=uuid4(),
        user_id=current_user.user_id,
        title=payload.title,
        brief=payload.brief,
        status=RunStatus.PENDING,
    )
    created = await project_repo.create(project)
    return to_project_summary_dto(created)


@router.get("", response_model=list[ProjectSummaryDTO])
async def list_projects(
    current_user: CurrentUserDep,
    project_repo: ProjectRepoDep,
) -> list[ProjectSummaryDTO]:
    """List all projects belonging to the authenticated user."""
    projects = await project_repo.list_by_user(current_user.user_id)
    return [to_project_summary_dto(project) for project in projects]


@router.get("/{project_id}", response_model=ProjectDetailDTO)
async def get_project(
    project_id: UUID,
    current_user: CurrentUserDep,
    project_repo: ProjectRepoDep,
    document_repo: DocumentRepoDep,
    agent_repo: AgentRepoDep,
    eval_repo: EvalRepoDep,
) -> ProjectDetailDTO:
    """Fetch full project state, attached documents, latest agent, and eval report."""
    project = await require_owned_project(project_repo, project_id, current_user.user_id)
    docs = await document_repo.list_by_project(project_id)
    latest_agent = await agent_repo.get_latest(project_id)
    honest_report = await eval_repo.get_honest_report(project_id)
    iterations = await eval_repo.list_iteration_logs(project_id)

    return ProjectDetailDTO(
        project=to_project_summary_dto(project),
        documents=[
            DocumentSummaryDTO(
                document_id=doc.id,
                filename=doc.filename,
                chunk_count=int(doc.metadata.get("chunk_count", 0)),
            )
            for doc in docs
        ],
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
        latest_agent=to_agent_dto(latest_agent) if latest_agent is not None else None,
        honest_report=to_honest_report_dto(honest_report) if honest_report is not None else None,
        iterations=[to_iteration_log_dto(log) for log in iterations],
    )
