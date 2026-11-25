"""PDF document parser using pdfplumber."""

from __future__ import annotations

from io import BytesIO

import pdfplumber

from app.domain.exceptions import ValidationDomainError


def _format_markdown_table(raw_table: list[list[str | None]]) -> str:
    """Convert a pdfplumber table matrix into a Markdown table string."""
    cleaned_rows: list[list[str]] = []
    for row in raw_table:
        cleaned = [str(cell).strip().replace("\n", " ") if cell is not None else "" for cell in row]
        if any(cleaned):
            cleaned_rows.append(cleaned)

    if not cleaned_rows:
        return ""

    col_count = max(len(row) for row in cleaned_rows)
    normalized = [row + [""] * (col_count - len(row)) for row in cleaned_rows]

    header = "| " + " | ".join(normalized[0]) + " |"
    separator = "| " + " | ".join("---" for _ in range(col_count)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in normalized[1:]]
    return "\n".join([header, separator, *body])


class PdfParser:
    """Extracts text and Markdown-formatted tables per page from PDF bytes."""

    def supports(self, mime_type: str, filename: str) -> bool:
        """Return True for application/pdf MIME type or .pdf filename."""
        return mime_type.lower() == "application/pdf" or filename.lower().endswith(".pdf")

    def parse(self, content: bytes, filename: str) -> str:
        """Extract normalized text and Markdown tables from PDF bytes."""
        if not content:
            raise ValidationDomainError("EMPTY_DOCUMENT", f"PDF '{filename}' has no content.")

        try:
            with pdfplumber.open(BytesIO(content)) as pdf:
                sections: list[str] = []
                for page_num, page in enumerate(pdf.pages, start=1):
                    parts: list[str] = []
                    page_text = (page.extract_text() or "").strip()
                    if page_text:
                        parts.append(page_text)

                    tables = page.extract_tables() or []
                    for raw_table in tables:
                        md_table = _format_markdown_table(raw_table)
                        if md_table:
                            parts.append(md_table)

                    if parts:
                        sections.append(f"[Page {page_num}]\n" + "\n\n".join(parts))

                return "\n\n".join(sections)
        except ValidationDomainError:
            raise
        except Exception as exc:
            raise ValidationDomainError(
                "PDF_PARSE_ERROR",
                f"Failed to parse PDF '{filename}': {exc}",
            ) from exc
