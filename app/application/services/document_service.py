"""Document ingestion service: parse -> chunk -> embed -> upsert."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.exceptions import ValidationDomainError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from app.domain.entities.document import DocumentChunk
    from app.domain.protocols.document_parser import DocumentParserProtocol
    from app.domain.protocols.llm_gateway import EmbeddingGatewayProtocol
    from app.domain.protocols.vector_store import VectorStoreProtocol
    from app.infrastructure.parsers.chunker import OverlapChunker


class DocumentService:
    """Orchestrates parsing, chunking, embedding, and indexing uploaded documents."""

    def __init__(
        self,
        parsers: Sequence[DocumentParserProtocol],
        chunker: OverlapChunker,
        embedding_gateway: EmbeddingGatewayProtocol,
        vector_store: VectorStoreProtocol,
    ) -> None:
        self._parsers = list(parsers)
        self._chunker = chunker
        self._embedding_gateway = embedding_gateway
        self._vector_store = vector_store

    def select_parser(self, mime_type: str, filename: str) -> DocumentParserProtocol:
        """Select the first registered parser supporting the given MIME type or filename."""
        for parser in self._parsers:
            if parser.supports(mime_type, filename):
                return parser
        raise ValidationDomainError(
            "UNSUPPORTED_DOCUMENT_TYPE",
            f"No parser supports filename='{filename}' with mime_type='{mime_type}'.",
        )

    async def ingest_document(
        self,
        *,
        project_id: UUID,
        document_id: UUID,
        filename: str,
        mime_type: str,
        content: bytes,
        chunk_size: int = 600,
        chunk_overlap: int = 100,
    ) -> list[DocumentChunk]:
        """Parse raw bytes, chunk text, generate embeddings, and upsert into vector store."""
        parser = self.select_parser(mime_type=mime_type, filename=filename)
        parsed_text = parser.parse(content, filename)

        chunks = self._chunker.chunk_text(
            text=parsed_text,
            document_id=document_id,
            project_id=project_id,
            filename=filename,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        if not chunks:
            return []

        embeddings = await self._embedding_gateway.embed_texts([chunk.content for chunk in chunks])
        if len(embeddings) != len(chunks):
            raise ValidationDomainError(
                "EMBEDDING_COUNT_MISMATCH",
                f"Expected {len(chunks)} embeddings, received {len(embeddings)}.",
            )

        for chunk, embedding in zip(chunks, embeddings, strict=True):
            chunk.embedding = embedding

        await self._vector_store.upsert_chunks(chunks)
        return chunks
