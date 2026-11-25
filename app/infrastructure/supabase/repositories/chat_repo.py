"""Supabase repository implementation for Conversation and Message entities."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

from app.domain.entities.conversation import Conversation, Message

if TYPE_CHECKING:
    from supabase import Client


class SupabaseChatRepository:
    """Supabase persistence adapter implementing ChatRepositoryProtocol."""

    _CONVERSATIONS_TABLE = "conversations"
    _MESSAGES_TABLE = "messages"

    def __init__(self, client: Client) -> None:
        self._client = client

    async def create_conversation(self, conversation: Conversation) -> Conversation:
        """Persist a new conversation."""
        payload = {
            "id": str(conversation.id),
            "project_id": str(conversation.project_id) if conversation.project_id else None,
            "agent_id": str(conversation.agent_id) if conversation.agent_id else None,
            "user_id": str(conversation.user_id) if conversation.user_id else None,
            "title": conversation.title,
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat(),
        }
        response = await asyncio.to_thread(
            lambda: self._client.table(self._CONVERSATIONS_TABLE).insert(payload).execute()
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return self._conv_from_row(rows[0]) if rows else conversation

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        """Fetch a conversation by its unique identifier."""
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self._CONVERSATIONS_TABLE)
                .select("*")
                .eq("id", str(conversation_id))
                .limit(1)
                .execute()
            )
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return self._conv_from_row(rows[0]) if rows else None

    async def add_message(self, message: Message) -> Message:
        """Append a message to a conversation."""
        payload = {
            "id": str(message.id),
            "conversation_id": str(message.conversation_id),
            "role": message.role,
            "content": message.content,
            "metadata": message.metadata,
            "created_at": message.created_at.isoformat(),
        }
        response = await asyncio.to_thread(
            lambda: self._client.table(self._MESSAGES_TABLE).insert(payload).execute()
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return self._msg_from_row(rows[0]) if rows else message

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        """List ordered messages belonging to a conversation."""
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self._MESSAGES_TABLE)
                .select("*")
                .eq("conversation_id", str(conversation_id))
                .order("created_at", desc=False)
                .execute()
            )
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return [self._msg_from_row(row) for row in rows]

    @staticmethod
    def _conv_from_row(row: dict[str, Any]) -> Conversation:
        return Conversation(
            id=UUID(str(row["id"])),
            project_id=UUID(str(row["project_id"])) if row.get("project_id") else None,
            agent_id=UUID(str(row["agent_id"])) if row.get("agent_id") else None,
            user_id=UUID(str(row["user_id"])) if row.get("user_id") else None,
            title=str(row["title"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )

    @staticmethod
    def _msg_from_row(row: dict[str, Any]) -> Message:
        return Message(
            id=UUID(str(row["id"])),
            conversation_id=UUID(str(row["conversation_id"])),
            role=cast('Literal["user", "assistant", "system"]', str(row["role"])),
            content=str(row["content"]),
            metadata=cast("dict[str, Any]", row.get("metadata") or {}),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )
