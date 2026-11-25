"""Shared domain-to-DTO mappers and ownership checks for presentation routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.dtos.agent_dtos import (
    AgentDefinitionDTO,
    OutputContractDTO,
    RetrievalConfigDTO,
)
from app.application.dtos.eval_dtos import (
    EvalCaseDTO,
    HonestReportDTO,
    IterationLogDTO,
)
from app.application.dtos.project_dtos import (
    ClarifyingQADTO,
    GroundabilityReportDTO,
    ProjectSummaryDTO,
    RequirementsDocDTO,
    TopicGroundabilityDTO,
)
from app.domain.exceptions import EntityNotFoundError
from app.domain.value_objects.enums import ProjectStatus, RunStatus

if TYPE_CHECKING:
    from uuid import UUID

    from app.domain.entities.agent_definition import AgentDefinition
    from app.domain.entities.evaluation import EvalCase, HonestReport, IterationLog
    from app.domain.entities.project import ForgeProject
    from app.domain.entities.requirements import GroundabilityReport, RequirementsDoc
    from app.domain.protocols.repositories import ProjectRepositoryProtocol


async def require_owned_project(
    project_repo: ProjectRepositoryProtocol,
    project_id: UUID,
    user_id: UUID,
) -> ForgeProject:
    """Fetch a project and ensure it exists and belongs to `user_id`."""
    project = await project_repo.get_by_id(project_id)
    if project is None or project.user_id != user_id:
        raise EntityNotFoundError("PROJECT_NOT_FOUND", f"Project '{project_id}' was not found.")
    return project


def map_project_status(project: ForgeProject) -> ProjectStatus:
    """Derive presentation ProjectStatus from ForgeProject state."""
    if project.groundability_report is not None and not project.groundability_report.is_passable:
        return ProjectStatus.BLOCKED
    mapping = {
        RunStatus.PENDING: (
            ProjectStatus.INTAKE if project.requirements_doc is not None else ProjectStatus.DRAFTING
        ),
        RunStatus.RUNNING: ProjectStatus.FORGING,
        RunStatus.COMPLETED: ProjectStatus.READY,
        RunStatus.STOPPED_EARLY: ProjectStatus.READY,
        RunStatus.FAILED: ProjectStatus.FAILED,
    }
    return mapping[project.status]


def to_project_summary_dto(project: ForgeProject) -> ProjectSummaryDTO:
    """Convert ForgeProject entity into ProjectSummaryDTO."""
    return ProjectSummaryDTO(
        id=project.id,
        user_id=project.user_id,
        title=project.title,
        brief=project.brief,
        status=map_project_status(project),
    )


def to_requirements_dto(req: RequirementsDoc) -> RequirementsDocDTO:
    """Convert RequirementsDoc entity into RequirementsDocDTO."""
    return RequirementsDocDTO(
        agent_name=req.agent_name,
        scope=req.scope,
        target_audience=req.target_audience,
        tone=req.tone,
        must_answer_topics=list(req.must_answer_topics),
        must_refuse_topics=list(req.must_refuse_topics),
        clarifying_qa=[
            ClarifyingQADTO(question=qa.question, answer=qa.answer) for qa in req.clarifying_qa
        ],
        detected_tool_needs=list(req.detected_tool_needs),
    )


def to_groundability_dto(report: GroundabilityReport) -> GroundabilityReportDTO:
    """Convert GroundabilityReport entity into GroundabilityReportDTO."""
    return GroundabilityReportDTO(
        is_passable=report.is_passable,
        critical_gaps=[
            TopicGroundabilityDTO(
                topic=item.topic,
                is_grounded=item.is_grounded,
                confidence=item.confidence,
                supporting_documents=list(item.supporting_documents),
                gap_reason=item.gap_reason,
            )
            for item in report.critical_gaps
        ],
        warnings=[
            TopicGroundabilityDTO(
                topic=item.topic,
                is_grounded=item.is_grounded,
                confidence=item.confidence,
                supporting_documents=list(item.supporting_documents),
                gap_reason=item.gap_reason,
            )
            for item in report.warnings
        ],
        summary=report.summary,
    )


def to_agent_dto(agent: AgentDefinition) -> AgentDefinitionDTO:
    """Convert AgentDefinition entity into AgentDefinitionDTO."""
    return AgentDefinitionDTO(
        id=agent.id,
        project_id=agent.project_id,
        slug=agent.slug,
        version=agent.version,
        system_prompt=agent.system_prompt,
        retrieval_config=RetrievalConfigDTO(
            chunk_size=agent.retrieval_config.chunk_size,
            chunk_overlap=agent.retrieval_config.chunk_overlap,
            top_k=agent.retrieval_config.top_k,
            similarity_threshold=agent.retrieval_config.similarity_threshold,
            hybrid_search=agent.retrieval_config.hybrid_search,
        ),
        selected_tools=list(agent.selected_tools),
        output_contract=OutputContractDTO(
            format=agent.output_contract.format,
            require_citations=agent.output_contract.require_citations,
            refusal_template=agent.output_contract.refusal_template,
            max_response_words=agent.output_contract.max_response_words,
        ),
        is_published=agent.is_published,
    )


def to_eval_case_dto(case: EvalCase) -> EvalCaseDTO:
    """Convert EvalCase entity into EvalCaseDTO."""
    return EvalCaseDTO(
        id=case.id,
        case_type=case.case_type,
        question=case.question,
        expected_sources=list(case.expected_sources),
        expected_facts=list(case.expected_facts),
        should_refuse=case.should_refuse,
        rationale=case.rationale,
    )


def to_iteration_log_dto(log: IterationLog) -> IterationLogDTO:
    """Convert IterationLog entity into IterationLogDTO."""
    return IterationLogDTO(
        iteration=log.iteration,
        score_before=log.score_before,
        score_after=log.score_after,
        failures_addressed=list(log.failures_addressed),
        change_type=log.change_type,
        what_changed=log.what_changed,
        why=log.why,
    )


def to_honest_report_dto(report: HonestReport) -> HonestReportDTO:
    """Convert HonestReport entity into HonestReportDTO."""
    return HonestReportDTO(
        project_id=report.project_id,
        final_agent_version=report.final_agent_version,
        per_iteration_scores=list(report.per_iteration_scores),
        final_pass_rate=report.final_pass_rate,
        remaining_failures=list(report.remaining_failures),
        known_limitations=list(report.known_limitations),
        recommendation=report.recommendation,
    )
