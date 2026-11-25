"""Domain repository protocol definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from uuid import UUID

    from app.domain.entities.agent_definition import AgentDefinition
    from app.domain.entities.conversation import Conversation, Message
    from app.domain.entities.document import Document
    from app.domain.entities.evaluation import (
        EvalCase,
        HonestReport,
        IterationLog,
        JudgeScore,
    )
    from app.domain.entities.project import ForgeProject


@runtime_checkable
class ProjectRepositoryProtocol(Protocol):
    """Port for persisting and querying ForgeAI projects."""

    async def create(self, project: ForgeProject) -> ForgeProject:
        """Persist a new ForgeAI project."""
        ...

    async def get_by_id(self, project_id: UUID) -> ForgeProject | None:
        """Fetch a project by its unique identifier."""
        ...

    async def list_by_user(self, user_id: UUID) -> list[ForgeProject]:
        """List all projects belonging to a user."""
        ...

    async def update(self, project: ForgeProject) -> ForgeProject:
        """Persist updates to an existing project."""
        ...


@runtime_checkable
class DocumentRepositoryProtocol(Protocol):
    """Port for persisting and querying uploaded project documents."""

    async def create(self, document: Document) -> Document:
        """Persist a new document record."""
        ...

    async def get_by_id(self, document_id: UUID) -> Document | None:
        """Fetch a document by its unique identifier."""
        ...

    async def list_by_project(self, project_id: UUID) -> list[Document]:
        """List all documents attached to a project."""
        ...

    async def get_by_hash(self, project_id: UUID, content_hash: str) -> Document | None:
        """Find an existing document in a project matching a content hash."""
        ...


@runtime_checkable
class AgentRepositoryProtocol(Protocol):
    """Port for persisting and querying versioned agent definitions."""

    async def save(self, agent: AgentDefinition) -> AgentDefinition:
        """Persist an agent definition version."""
        ...

    async def get_latest(self, project_id: UUID) -> AgentDefinition | None:
        """Fetch the latest agent definition version for a project."""
        ...

    async def get_by_slug(self, slug: str) -> AgentDefinition | None:
        """Fetch the latest published agent definition by its public slug."""
        ...

    async def list_versions(self, project_id: UUID) -> list[AgentDefinition]:
        """List all agent definition versions for a project."""
        ...


@runtime_checkable
class EvalRepositoryProtocol(Protocol):
    """Port for persisting evaluation cases, judge scores, iterations, and reports."""

    async def save_eval_cases(self, project_id: UUID, cases: list[EvalCase]) -> None:
        """Persist generated evaluation cases for a project."""
        ...

    async def list_eval_cases(self, project_id: UUID) -> list[EvalCase]:
        """List evaluation cases for a project."""
        ...

    async def save_judge_scores(
        self,
        project_id: UUID,
        iteration: int,
        scores: list[JudgeScore],
    ) -> None:
        """Persist judge scores for a specific optimization iteration."""
        ...

    async def save_iteration_log(self, project_id: UUID, log: IterationLog) -> None:
        """Persist a single critic-optimizer iteration log."""
        ...

    async def list_iteration_logs(self, project_id: UUID) -> list[IterationLog]:
        """List all critic-optimizer iteration logs for a project."""
        ...

    async def save_honest_report(self, report: HonestReport) -> None:
        """Persist the final honest report for a project."""
        ...

    async def get_honest_report(self, project_id: UUID) -> HonestReport | None:
        """Fetch the final honest report for a project if available."""
        ...


@runtime_checkable
class ChatRepositoryProtocol(Protocol):
    """Port for persisting runnable agent conversations and messages."""

    async def create_conversation(self, conversation: Conversation) -> Conversation:
        """Persist a new conversation."""
        ...

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        """Fetch a conversation by its unique identifier."""
        ...

    async def add_message(self, message: Message) -> Message:
        """Append a message to a conversation."""
        ...

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        """List ordered messages belonging to a conversation."""
        ...
