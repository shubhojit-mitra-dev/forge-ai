"""Unit tests for infrastructure document parsers and chunker."""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.domain.entities.document import DocumentChunk
from app.domain.exceptions import ValidationDomainError
from app.domain.protocols.document_parser import DocumentParserProtocol
from app.infrastructure.parsers import CsvParser, OverlapChunker, PdfParser, TextParser


class TestPdfParser:
    def test_implements_document_parser_protocol(self) -> None:
        parser = PdfParser()
        assert isinstance(parser, DocumentParserProtocol)

    def test_supports_pdf_mime_and_extension(self) -> None:
        parser = PdfParser()
        assert parser.supports("application/pdf", "manual.dat") is True
        assert parser.supports("application/octet-stream", "Report.PDF") is True
        assert parser.supports("text/plain", "notes.txt") is False
        assert parser.supports("text/csv", "data.csv") is False

    def test_parse_multipage_text_and_markdown_tables(self) -> None:
        page_1 = MagicMock()
        page_1.extract_text.return_value = "Engine Cooling Manual\nSection 1"
        page_1.extract_tables.return_value = [
            [
                ["Part No", "Description", "Qty"],
                ["SP-101", "Impeller\nKit", "2"],
                ["SP-102", None, "5"],
            ]
        ]

        page_2 = MagicMock()
        page_2.extract_text.return_value = "Maintenance Schedule"
        page_2.extract_tables.return_value = []

        mock_pdf = MagicMock()
        mock_pdf.pages = [page_1, page_2]
        mock_pdf.__enter__.return_value = mock_pdf
        mock_pdf.__exit__.return_value = None

        parser = PdfParser()
        with patch("app.infrastructure.parsers.pdf_parser.pdfplumber.open", return_value=mock_pdf):
            result = parser.parse(b"%PDF-1.4 fake bytes", "manual.pdf")

        assert "[Page 1]" in result
        assert "Engine Cooling Manual" in result
        assert "| Part No | Description | Qty |" in result
        assert "| --- | --- | --- |" in result
        assert "| SP-101 | Impeller Kit | 2 |" in result
        assert "| SP-102 |  | 5 |" in result
        assert "[Page 2]" in result
        assert "Maintenance Schedule" in result

    def test_parse_empty_bytes_raises_validation_error(self) -> None:
        parser = PdfParser()
        with pytest.raises(ValidationDomainError) as exc_info:
            parser.parse(b"", "empty.pdf")
        assert exc_info.value.code == "EMPTY_DOCUMENT"

    def test_parse_corrupt_pdf_raises_validation_error(self) -> None:
        parser = PdfParser()
        with (
            patch(
                "app.infrastructure.parsers.pdf_parser.pdfplumber.open",
                side_effect=RuntimeError("corrupt pdf"),
            ),
            pytest.raises(ValidationDomainError) as exc_info,
        ):
            parser.parse(b"not-a-pdf", "broken.pdf")
        assert exc_info.value.code == "PDF_PARSE_ERROR"


class TestCsvParser:
    def test_implements_document_parser_protocol(self) -> None:
        parser = CsvParser()
        assert isinstance(parser, DocumentParserProtocol)

    def test_supports_csv_mime_and_extension(self) -> None:
        parser = CsvParser()
        assert parser.supports("text/csv", "spares.dat") is True
        assert parser.supports("application/octet-stream", "inventory.CSV") is True
        assert parser.supports("application/pdf", "manual.pdf") is False
        assert parser.supports("text/plain", "readme.txt") is False

    def test_parse_formats_schema_header_and_rows(self) -> None:
        csv_bytes = b" part_no , name , stock \n00123, Main Valve , 4 \n00456, Seal Ring , 12 \n"
        parser = CsvParser()
        result = parser.parse(csv_bytes, "ship_spares.csv")

        lines = result.splitlines()
        assert lines[0] == "File: ship_spares.csv | Rows: 2 | Columns: part_no, name, stock"
        assert lines[1] == "Row 1: part_no: 00123 | name: Main Valve | stock: 4"
        assert lines[2] == "Row 2: part_no: 00456 | name: Seal Ring | stock: 12"

    def test_parse_empty_csv_returns_empty_string(self) -> None:
        parser = CsvParser()
        assert parser.parse(b"   \n  ", "empty.csv") == ""

    def test_parse_invalid_utf8_raises_validation_error(self) -> None:
        parser = CsvParser()
        with pytest.raises(ValidationDomainError) as exc_info:
            parser.parse(b"\xff\xfe\x00\x00", "bad.csv")
        assert exc_info.value.code == "CSV_PARSE_ERROR"


class TestTextParser:
    def test_implements_document_parser_protocol(self) -> None:
        parser = TextParser()
        assert isinstance(parser, DocumentParserProtocol)

    def test_supports_text_and_markdown_extensions_and_mimes(self) -> None:
        parser = TextParser()
        assert parser.supports("text/plain", "notes.txt") is True
        assert parser.supports("text/markdown", "README.md") is True
        assert parser.supports("application/octet-stream", "guide.markdown") is True
        assert parser.supports("application/pdf", "doc.pdf") is False
        assert parser.supports("text/csv", "table.csv") is False

    def test_parse_normalizes_line_endings_and_bom(self) -> None:
        raw = "\ufeffLine one\r\nLine two\rLine three\n  ".encode()
        parser = TextParser()
        result = parser.parse(raw, "notes.md")
        assert result == "Line one\nLine two\nLine three"

    def test_parse_invalid_utf8_raises_validation_error(self) -> None:
        parser = TextParser()
        with pytest.raises(ValidationDomainError) as exc_info:
            parser.parse(b"\x80\x81\x82", "corrupt.txt")
        assert exc_info.value.code == "TEXT_DECODE_ERROR"


class TestOverlapChunker:
    def test_empty_text_returns_no_chunks(self) -> None:
        chunker = OverlapChunker()
        assert chunker.chunk_text("   \n\t ", uuid4(), uuid4(), "empty.txt") == []

    def test_single_chunk_preserves_metadata_hash_and_tokens(self) -> None:
        chunker = OverlapChunker()
        doc_id = uuid4()
        project_id = uuid4()
        text = "ForgeAI builds honest, grounded AI agents."

        chunks = chunker.chunk_text(
            text=text,
            document_id=doc_id,
            project_id=project_id,
            filename="brief.md",
            chunk_size=600,
            chunk_overlap=100,
        )

        assert len(chunks) == 1
        chunk = chunks[0]
        assert isinstance(chunk, DocumentChunk)
        assert chunk.document_id == doc_id
        assert chunk.project_id == project_id
        assert chunk.chunk_index == 0
        assert chunk.content == text
        assert chunk.content_hash == hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert chunk.token_count == len(text) // 4
        assert chunk.metadata["filename"] == "brief.md"
        assert chunk.metadata["chunk_index"] == 0

    def test_overlapping_chunks_preserve_continuity_and_bounds(self) -> None:
        chunker = OverlapChunker()
        doc_id = uuid4()
        project_id = uuid4()
        words = [f"word{i:03d}" for i in range(60)]
        text = " ".join(words)

        chunks = chunker.chunk_text(
            text=text,
            document_id=doc_id,
            project_id=project_id,
            filename="long.txt",
            chunk_size=120,
            chunk_overlap=30,
        )

        assert len(chunks) > 2
        for idx, chunk in enumerate(chunks):
            assert chunk.chunk_index == idx
            assert len(chunk.content) <= 120
            assert chunk.content_hash == hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
            assert chunk.token_count == len(chunk.content) // 4
            assert chunk.metadata["filename"] == "long.txt"

        # Consecutive chunks should share overlapping content
        overlap_tail = chunks[0].content[-15:]
        assert overlap_tail in chunks[1].content

    @pytest.mark.parametrize(
        ("chunk_size", "chunk_overlap", "expected_code"),
        [
            (0, 0, "INVALID_CHUNK_SIZE"),
            (-10, 0, "INVALID_CHUNK_SIZE"),
            (100, -1, "INVALID_CHUNK_OVERLAP"),
            (100, 100, "INVALID_CHUNK_OVERLAP"),
            (100, 150, "INVALID_CHUNK_OVERLAP"),
        ],
    )
    def test_invalid_chunk_parameters_raise_validation_error(
        self, chunk_size: int, chunk_overlap: int, expected_code: str
    ) -> None:
        chunker = OverlapChunker()
        with pytest.raises(ValidationDomainError) as exc_info:
            chunker.chunk_text(
                text="Some valid text",
                document_id=uuid4(),
                project_id=uuid4(),
                filename="doc.txt",
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        assert exc_info.value.code == expected_code
