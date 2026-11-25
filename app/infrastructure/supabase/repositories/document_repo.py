"""Supabase repository implementation for Document entities."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from app.domain.entities.document import Document

if TYPE_CHECKING:
    from supabase import Client


class SupabaseDocumentRepository:
    """Supabase persistence adapter implementing DocumentRepositoryProtocol."""

    _TABLE = "documents"

    def __init__(self, client: Client) -> None:
        self._client = client

    async def create(self, document: Document) -> Document:
        """Persist a new document record."""
        payload = self._to_row(document)
        response = await asyncio.to_thread(
            lambda: self._client.table(self._TABLE).insert(payload).execute()
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return self._from_row(rows[0]) if rows else document

    async def get_by_id(self, document_id: UUID) -> Document | None:
        """Fetch a document by its unique identifier."""
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self._TABLE)
                .select("*")
                .eq("id", str(document_id))
                .limit(1)
                .execute()
            )
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return self._from_row(rows[0]) if rows else None

    async def list_by_project(self, project_id: UUID) -> list[Document]:
        """List all documents attached to a project."""
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self._TABLE)
                .select("*")
                .eq("project_id", str(project_id))
                .order("created_at", desc=False)
                .execute()
            )
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return [self._from_row(row) for row in rows]

    async def get_by_hash(self, project_id: UUID, content_hash: str) -> Document | None:
        """Find an existing document in a project matching a content hash."""
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self._TABLE)
                .select("*")
                .eq("project_id", str(project_id))
                .eq("content_hash", content_hash)
                .limit(1)
                .execute()
            )
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return self._from_row(rows[0]) if rows else None

    @staticmethod
    def _to_row(document: Document) -> dict[str, Any]:
        return {
            "id": str(document.id),
            "project_id": str(document.project_id),
            "filename": document.filename,
            "mime_type": document.mime_type,
            "storage_path": document.storage_path,
            "content_hash": document.content_hash,
            "metadata": document.metadata,
            "created_at": document.created_at.isoformat(),
        }

    @staticmethod
    def _from_row(row: dict[str, Any]) -> Document:
        return Document(
            id=UUID(str(row["id"])),
            project_id=UUID(str(row["project_id"])),
            filename=str(row["filename"]),
            mime_type=str(row["mime_type"]),
            storage_path=str(row["storage_path"]),
            content_hash=str(row["content_hash"]),
            metadata=cast("dict[str, Any]", row.get("metadata") or {}),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )
