"""Plain-text and Markdown document parser."""

from __future__ import annotations

from app.domain.exceptions import ValidationDomainError

_TEXT_MIME_TYPES = frozenset({"text/plain", "text/markdown", "text/x-markdown"})
_TEXT_EXTENSIONS = (".txt", ".md", ".markdown")


class TextParser:
    """Extracts normalized UTF-8 text from .txt, .md, and .markdown files."""

    def supports(self, mime_type: str, filename: str) -> bool:
        """Return True for supported text/markdown MIME types or extensions."""
        return mime_type.lower() in _TEXT_MIME_TYPES or filename.lower().endswith(_TEXT_EXTENSIONS)

    def parse(self, content: bytes, filename: str) -> str:
        """Decode UTF-8 bytes (stripping BOM) and normalize line endings."""
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationDomainError(
                "TEXT_DECODE_ERROR",
                f"Failed to decode text document '{filename}' as UTF-8: {exc}",
            ) from exc

        return decoded.replace("\r\n", "\n").replace("\r", "\n").strip()
