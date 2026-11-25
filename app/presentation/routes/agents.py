"""Public runnable agent metadata and chat routes."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.application.dtos.agent_dtos import OutputContractDTO
from app.application.services.chat_runner_service import ChatResponse
from app.domain.exceptions import EntityNotFoundError
from app.domain.value_objects.enums import ToolName
from app.presentation.dependencies import AgentRepoDep, ChatRunnerServiceDep

router = APIRouter(prefix="/agents/public", tags=["public-agents"])


class PublicAgentMetadataDTO(BaseModel):
    """Public metadata for rendering `/agent/[slug]` UI."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    project_id: UUID
    slug: Annotated[str, Field(min_length=1)]
    version: Annotated[int, Field(ge=1)]
    selected_tools: list[ToolName]
    output_contract: OutputContractDTO


class PublicChatRequestDTO(BaseModel):
    """Chat request payload for a published runnable agent."""

    model_config = ConfigDict(frozen=True)

    message: Annotated[str, Field(min_length=1)]
    history: list[dict[str, str]] | None = None
    tool_calls: list[dict[str, Any]] | None = None


@router.get("/{slug}", response_model=PublicAgentMetadataDTO)
async def get_public_agent(
    slug: str,
    agent_repo: AgentRepoDep,
) -> PublicAgentMetadataDTO:
    """Fetch public metadata for a published agent by slug."""
    agent = await agent_repo.get_by_slug(slug)
    if agent is None:
        raise EntityNotFoundError("AGENT_NOT_FOUND", f"Published agent '{slug}' was not found.")

    return PublicAgentMetadataDTO(
        id=agent.id,
        project_id=agent.project_id,
        slug=agent.slug,
        version=agent.version,
        selected_tools=list(agent.selected_tools),
        output_contract=OutputContractDTO(
            format=agent.output_contract.format,
            require_citations=agent.output_contract.require_citations,
            refusal_template=agent.output_contract.refusal_template,
            max_response_words=agent.output_contract.max_response_words,
        ),
    )


@router.post("/{slug}/chat", response_model=ChatResponse)
async def chat_with_public_agent(
    slug: str,
    payload: PublicChatRequestDTO,
    agent_repo: AgentRepoDep,
    chat_runner: ChatRunnerServiceDep,
) -> ChatResponse:
    """Execute a chat turn against a published runnable agent."""
    agent = await agent_repo.get_by_slug(slug)
    if agent is None:
        raise EntityNotFoundError("AGENT_NOT_FOUND", f"Published agent '{slug}' was not found.")

    return await chat_runner.run(
        agent_def=agent,
        user_message=payload.message,
        history=payload.history,
        tool_calls=payload.tool_calls,
    )
