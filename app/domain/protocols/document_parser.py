"""Document parser protocol definition."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DocumentParserProtocol(Protocol):
    """Port for extracting plain text from uploaded document bytes."""

    def supports(self, mime_type: str, filename: str) -> bool:
        """Return True if this parser handles the given MIME type or filename."""
        ...

    def parse(self, content: bytes, filename: str) -> str:
        """Extract normalized text content from raw document bytes."""
        ...
