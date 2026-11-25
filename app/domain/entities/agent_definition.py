from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from app.domain.value_objects.enums import ToolName


@dataclass(slots=True, frozen=True)
class RetrievalConfig:
    """Immutable retrieval hyperparameters for an AgentDefinition."""

    chunk_size: int = 600
    chunk_overlap: int = 100
    top_k: int = 5
    similarity_threshold: float = 0.35
    hybrid_search: bool = True

    def __post_init__(self) -> None:
        if not 200 <= self.chunk_size <= 2000:
            raise ValueError("chunk_size must be between 200 and 2000")
        if not 0 <= self.chunk_overlap <= 400:
            raise ValueError("chunk_overlap must be between 0 and 400")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        if not 1 <= self.top_k <= 15:
            raise ValueError("top_k must be between 1 and 15")
        if not 0.0 <= self.similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be between 0.0 and 1.0")


@dataclass(slots=True, frozen=True)
class OutputContract:
    """Immutable response formatting and refusal contract for an AgentDefinition."""

    format: Literal["markdown", "json"] = "markdown"
    require_citations: bool = True
    refusal_template: str = "I cannot answer this based on the provided documents."
    max_response_words: int = 350

    def __post_init__(self) -> None:
        if not 50 <= self.max_response_words <= 1000:
            raise ValueError("max_response_words must be between 50 and 1000")


@dataclass(slots=True)
class AgentDefinition:
    """Versioned specification of a generated runnable AI agent."""

    id: UUID
    project_id: UUID
    slug: str
    version: int
    system_prompt: str
    retrieval_config: RetrievalConfig
    selected_tools: list[ToolName]
    output_contract: OutputContract
    is_published: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("version must be >= 1")

    def bump_version(
        self,
        *,
        system_prompt: str | None = None,
        retrieval_config: RetrievalConfig | None = None,
        selected_tools: list[ToolName] | None = None,
        output_contract: OutputContract | None = None,
        is_published: bool | None = None,
    ) -> "AgentDefinition":
        """Return a new AgentDefinition with version incremented by 1."""
        return AgentDefinition(
            id=self.id,
            project_id=self.project_id,
            slug=self.slug,
            version=self.version + 1,
            system_prompt=system_prompt if system_prompt is not None else self.system_prompt,
            retrieval_config=(
                retrieval_config if retrieval_config is not None else self.retrieval_config
            ),
            selected_tools=(
                list(selected_tools) if selected_tools is not None else list(self.selected_tools)
            ),
            output_contract=(
                output_contract if output_contract is not None else self.output_contract
            ),
            is_published=is_published if is_published is not None else self.is_published,
        )
