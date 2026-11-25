"""Vector store protocol definition for chunk persistence and hybrid search."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from uuid import UUID

    from app.domain.entities.document import DocumentChunk


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """Port for storing and retrieving embedded document chunks."""

    async def upsert_chunks(self, chunks: list[DocumentChunk]) -> None:
        """Insert or update document chunks and their vector embeddings."""
        ...

    async def hybrid_search(
        self,
        project_id: UUID,
        query_text: str,
        query_embedding: list[float],
        top_k: int = 5,
        similarity_threshold: float = 0.35,
    ) -> list[DocumentChunk]:
        """Search chunks using combined semantic and keyword relevance."""
        ...
