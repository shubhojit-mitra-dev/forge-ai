from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID


@dataclass(slots=True)
class Conversation:
    """Chat session for either ForgeAI builder or a published runnable agent."""

    id: UUID
    project_id: UUID | None
    agent_id: UUID | None
    user_id: UUID | None
    title: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class Message:
    """Single message within a Conversation."""

    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
