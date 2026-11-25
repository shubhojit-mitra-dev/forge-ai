"""Overlapping text chunker producing DocumentChunk domain entities."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING
from uuid import uuid4

from app.domain.entities.document import DocumentChunk
from app.domain.exceptions import ValidationDomainError

if TYPE_CHECKING:
    from uuid import UUID


class OverlapChunker:
    """Splits normalized document text into overlapping DocumentChunk entities."""

    def chunk_text(
        self,
        text: str,
        document_id: UUID,
        project_id: UUID,
        filename: str,
        chunk_size: int = 600,
        chunk_overlap: int = 100,
    ) -> list[DocumentChunk]:
        """Split text into overlapping chunks with SHA-256 content hashes."""
        if chunk_size <= 0:
            raise ValidationDomainError("INVALID_CHUNK_SIZE", "chunk_size must be positive.")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValidationDomainError(
                "INVALID_CHUNK_OVERLAP",
                "chunk_overlap must be >= 0 and < chunk_size.",
            )

        normalized = text.strip()
        if not normalized:
            return []

        chunks: list[DocumentChunk] = []
        total_len = len(normalized)
        start = 0
        chunk_index = 0

        while start < total_len:
            raw_end = min(start + chunk_size, total_len)
            end = self._find_split_boundary(normalized, start, raw_end, total_len, chunk_size)
            chunk_content = normalized[start:end].strip()

            if chunk_content:
                content_hash = hashlib.sha256(chunk_content.encode("utf-8")).hexdigest()
                chunks.append(
                    DocumentChunk(
                        id=uuid4(),
                        document_id=document_id,
                        project_id=project_id,
                        chunk_index=chunk_index,
                        content=chunk_content,
                        content_hash=content_hash,
                        token_count=len(chunk_content) // 4,
                        metadata={
                            "filename": filename,
                            "chunk_index": chunk_index,
                            "char_start": start,
                            "char_end": end,
                        },
                    )
                )
                chunk_index += 1

            if end >= total_len:
                break

            next_start = end - chunk_overlap
            if next_start <= start:
                next_start = end
            start = next_start

        return chunks

    @staticmethod
    def _find_split_boundary(
        text: str,
        start: int,
        raw_end: int,
        total_len: int,
        chunk_size: int,
    ) -> int:
        """Prefer breaking on paragraph, newline, or space near raw_end."""
        if raw_end >= total_len:
            return total_len

        lookback = min(100, chunk_size // 4)
        min_pos = max(start + 1, raw_end - lookback)
        for sep in ("\n\n", "\n", " "):
            pos = text.rfind(sep, min_pos, raw_end)
            if pos > start:
                return pos + len(sep)
        return raw_end
