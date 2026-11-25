from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class Document:
    """Uploaded source document belonging to a ForgeAI project."""

    id: UUID
    project_id: UUID
    filename: str
    mime_type: str
    storage_path: str
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class DocumentChunk:
    """Indexed text chunk extracted from a Document for hybrid RAG."""

    id: UUID
    document_id: UUID
    project_id: UUID
    chunk_index: int
    content: str
    content_hash: str
    token_count: int
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    similarity: float = 0.0
    rrf_score: float = 0.0
