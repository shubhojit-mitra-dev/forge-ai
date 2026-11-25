"""Supabase pgvector store implementing VectorStoreProtocol."""

from __future__ import annotations

import asyncio
import hashlib
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from app.domain.entities.document import DocumentChunk

if TYPE_CHECKING:
    from supabase import Client


def _compute_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class PgVectorStore:
    """Postgres + pgvector adapter with content-hash deduplication and hybrid search."""

    _TABLE = "document_chunks"
    _HYBRID_RPC = "match_document_chunks_hybrid"

    def __init__(self, client: Client) -> None:
        self._client = client

    async def upsert_chunks(self, chunks: list[DocumentChunk]) -> None:
        """Insert or update document chunks, deduplicating embeddings by content_hash."""
        if not chunks:
            return

        unique_by_hash: dict[str, DocumentChunk] = {}
        for chunk in chunks:
            content_hash = chunk.content_hash or _compute_content_hash(chunk.content)
            if content_hash not in unique_by_hash:
                unique_by_hash[content_hash] = DocumentChunk(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    project_id=chunk.project_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    content_hash=content_hash,
                    token_count=chunk.token_count,
                    embedding=chunk.embedding,
                    metadata=chunk.metadata,
                    similarity=chunk.similarity,
                    rrf_score=chunk.rrf_score,
                )

        hashes = list(unique_by_hash.keys())
        existing_resp = await asyncio.to_thread(
            lambda: (
                self._client.table(self._TABLE)
                .select("content_hash")
                .in_("content_hash", hashes)
                .execute()
            )
        )
        existing_rows = cast("list[dict[str, Any]]", existing_resp.data or [])
        existing_hashes = {str(row["content_hash"]) for row in existing_rows}

        rows_to_upsert = [
            {
                "id": str(chunk.id),
                "document_id": str(chunk.document_id),
                "project_id": str(chunk.project_id),
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "content_hash": chunk.content_hash,
                "token_count": chunk.token_count,
                "embedding": chunk.embedding,
                "metadata": chunk.metadata,
            }
            for content_hash, chunk in unique_by_hash.items()
            if content_hash not in existing_hashes
        ]

        if not rows_to_upsert:
            return

        await asyncio.to_thread(
            lambda: self._client.table(self._TABLE).upsert(rows_to_upsert).execute()
        )

    async def hybrid_search(
        self,
        project_id: UUID,
        query_text: str,
        query_embedding: list[float],
        top_k: int = 5,
        similarity_threshold: float = 0.35,
    ) -> list[DocumentChunk]:
        """Search chunks using combined semantic and keyword relevance via RPC."""
        params: dict[str, Any] = {
            "p_project_id": str(project_id),
            "p_query_text": query_text,
            "p_query_embedding": query_embedding,
            "p_match_count": top_k,
            "p_similarity_threshold": similarity_threshold,
        }
        response = await asyncio.to_thread(
            lambda: self._client.rpc(self._HYBRID_RPC, params).execute()
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return [self._row_to_chunk(row) for row in rows]

    @staticmethod
    def _row_to_chunk(row: dict[str, Any]) -> DocumentChunk:
        return DocumentChunk(
            id=UUID(str(row["id"])),
            document_id=UUID(str(row["document_id"])),
            project_id=UUID(str(row["project_id"])),
            chunk_index=int(row["chunk_index"]),
            content=str(row["content"]),
            content_hash=str(row.get("content_hash", "")),
            token_count=int(row.get("token_count", 0)),
            embedding=cast("list[float] | None", row.get("embedding")),
            metadata=cast("dict[str, Any]", row.get("metadata") or {}),
            similarity=float(row.get("similarity", 0.0)),
            rrf_score=float(row.get("rrf_score", 0.0)),
        )
