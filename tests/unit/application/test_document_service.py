"""Unit tests for DocumentService (parse -> chunk -> embed -> upsert)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.services.document_service import DocumentService
from app.domain.exceptions import ValidationDomainError
from app.infrastructure.parsers.chunker import OverlapChunker


@pytest.mark.unit
async def test_ingest_document_parses_chunks_embeds_and_upserts() -> None:
    project_id = uuid4()
    document_id = uuid4()

    pdf_parser = MagicMock()
    pdf_parser.supports.return_value = False

    md_parser = MagicMock()
    md_parser.supports.side_effect = lambda mime, name: name.endswith(".md")
    md_parser.parse.return_value = (
        "Employees receive 20 days of paid time off per year. "
        "Unused PTO up to 5 days carries over into Q1."
    )

    embedding_gateway = AsyncMock()
    embedding_gateway.embed_texts.return_value = [[0.1, 0.2, 0.3]]

    vector_store = AsyncMock()

    service = DocumentService(
        parsers=[pdf_parser, md_parser],
        chunker=OverlapChunker(),
        embedding_gateway=embedding_gateway,
        vector_store=vector_store,
    )

    chunks = await service.ingest_document(
        project_id=project_id,
        document_id=document_id,
        filename="pto_policy.md",
        mime_type="text/markdown",
        content=b"raw bytes",
    )

    assert len(chunks) == 1
    assert chunks[0].project_id == project_id
    assert chunks[0].document_id == document_id
    assert chunks[0].embedding == [0.1, 0.2, 0.3]
    assert chunks[0].metadata["filename"] == "pto_policy.md"

    md_parser.parse.assert_called_once_with(b"raw bytes", "pto_policy.md")
    embedding_gateway.embed_texts.assert_awaited_once_with([chunks[0].content])
    vector_store.upsert_chunks.assert_awaited_once_with(chunks)


@pytest.mark.unit
async def test_ingest_document_unsupported_type_raises_validation_error() -> None:
    parser = MagicMock()
    parser.supports.return_value = False

    service = DocumentService(
        parsers=[parser],
        chunker=OverlapChunker(),
        embedding_gateway=AsyncMock(),
        vector_store=AsyncMock(),
    )

    with pytest.raises(ValidationDomainError) as exc_info:
        await service.ingest_document(
            project_id=uuid4(),
            document_id=uuid4(),
            filename="archive.zip",
            mime_type="application/zip",
            content=b"PK...",
        )

    assert exc_info.value.code == "UNSUPPORTED_DOCUMENT_TYPE"


@pytest.mark.unit
async def test_ingest_document_empty_parsed_text_skips_embed_and_upsert() -> None:
    parser = MagicMock()
    parser.supports.return_value = True
    parser.parse.return_value = "   \n\t  "

    embedding_gateway = AsyncMock()
    vector_store = AsyncMock()

    service = DocumentService(
        parsers=[parser],
        chunker=OverlapChunker(),
        embedding_gateway=embedding_gateway,
        vector_store=vector_store,
    )

    chunks = await service.ingest_document(
        project_id=uuid4(),
        document_id=uuid4(),
        filename="empty.txt",
        mime_type="text/plain",
        content=b"   ",
    )

    assert chunks == []
    embedding_gateway.embed_texts.assert_not_awaited()
    vector_store.upsert_chunks.assert_not_awaited()
