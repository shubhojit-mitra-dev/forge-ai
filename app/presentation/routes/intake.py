"""Stage 1 Intake and Stage 2 Groundability routes."""

from uuid import UUID

from fastapi import APIRouter

from app.application.dtos.project_dtos import (
    IntakeStartResponseDTO,
    IntakeSubmitRequestDTO,
    IntakeSubmitResponseDTO,
)
from app.domain.entities.requirements import ClarifyingQA
from app.presentation.dependencies import (
    CurrentUserDep,
    DocumentRepoDep,
    GroundabilityServiceDep,
    IntakeServiceDep,
    ProjectRepoDep,
)
from app.presentation.routes._mappers import (
    require_owned_project,
    to_groundability_dto,
    to_requirements_dto,
)

router = APIRouter(prefix="/projects/{project_id}/intake", tags=["intake"])


@router.post("/start", response_model=IntakeStartResponseDTO)
async def start_intake(
    project_id: UUID,
    current_user: CurrentUserDep,
    project_repo: ProjectRepoDep,
    document_repo: DocumentRepoDep,
    intake_service: IntakeServiceDep,
) -> IntakeStartResponseDTO:
    """Generate up to 5 clarifying questions from the project brief and uploaded docs."""
    project = await require_owned_project(project_repo, project_id, current_user.user_id)
    docs = await document_repo.list_by_project(project_id)
    doc_summaries = [doc.filename for doc in docs]

    questions = await intake_service.generate_questions(
        brief=project.brief,
        doc_summaries=doc_summaries,
    )
    return IntakeStartResponseDTO(project_id=project_id, questions=questions)


@router.post("/submit", response_model=IntakeSubmitResponseDTO)
async def submit_intake(
    project_id: UUID,
    payload: IntakeSubmitRequestDTO,
    current_user: CurrentUserDep,
    project_repo: ProjectRepoDep,
    document_repo: DocumentRepoDep,
    intake_service: IntakeServiceDep,
    groundability_service: GroundabilityServiceDep,
) -> IntakeSubmitResponseDTO:
    """Finalize RequirementsDoc and run Stage 2 GroundabilityGuard."""
    project = await require_owned_project(project_repo, project_id, current_user.user_id)
    docs = await document_repo.list_by_project(project_id)
    doc_summaries = [doc.filename for doc in docs]

    qa_pairs = [
        ClarifyingQA(question=item.question, answer=item.answer) for item in payload.qa_pairs
    ]
    requirements = await intake_service.finalize_requirements(
        brief=project.brief,
        doc_summaries=doc_summaries,
        qa_pairs=qa_pairs,
    )
    groundability = await groundability_service.evaluate(
        project_id=project_id,
        requirements=requirements,
    )

    project.requirements_doc = requirements
    project.groundability_report = groundability
    await project_repo.update(project)

    return IntakeSubmitResponseDTO(
        requirements=to_requirements_dto(requirements),
        groundability=to_groundability_dto(groundability),
    )
