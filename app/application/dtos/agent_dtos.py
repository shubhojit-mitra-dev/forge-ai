"""Pydantic v2 DTOs for ForgeAI agent definitions and configurations."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.value_objects.enums import ToolName


class RetrievalConfigDTO(BaseModel):
    """Immutable retrieval hyperparameters for an AgentDefinition."""

    model_config = ConfigDict(frozen=True)

    chunk_size: Annotated[int, Field(ge=200, le=2000)] = 600
    chunk_overlap: Annotated[int, Field(ge=0, le=400)] = 100
    top_k: Annotated[int, Field(ge=1, le=15)] = 5
    similarity_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.35
    hybrid_search: bool = True


class OutputContractDTO(BaseModel):
    """Immutable response formatting and refusal contract for an AgentDefinition."""

    model_config = ConfigDict(frozen=True)

    format: Literal["markdown", "json"] = "markdown"
    require_citations: bool = True
    refusal_template: Annotated[str, Field(min_length=1)] = (
        "I cannot answer this based on the provided documents."
    )
    max_response_words: Annotated[int, Field(ge=50, le=1000)] = 350


class AgentDefinitionDTO(BaseModel):
    """Versioned specification of a generated runnable AI agent."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    project_id: UUID
    slug: Annotated[str, Field(min_length=1)]
    version: Annotated[int, Field(ge=1)]
    system_prompt: Annotated[str, Field(min_length=50)]
    retrieval_config: RetrievalConfigDTO
    selected_tools: list[ToolName]
    output_contract: OutputContractDTO
    is_published: bool = False
