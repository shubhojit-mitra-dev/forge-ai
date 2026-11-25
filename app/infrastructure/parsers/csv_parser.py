"""CSV document parser using pandas."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from app.domain.exceptions import ValidationDomainError

_CSV_MIME_TYPES = frozenset({"text/csv", "application/csv", "application/vnd.ms-excel"})


class CsvParser:
    """Extracts schema header and clean row records from CSV bytes."""

    def supports(self, mime_type: str, filename: str) -> bool:
        """Return True for CSV MIME types or .csv filename."""
        return mime_type.lower() in _CSV_MIME_TYPES or filename.lower().endswith(".csv")

    def parse(self, content: bytes, filename: str) -> str:
        """Parse CSV bytes into a schema summary followed by clean row records."""
        if not content.strip():
            return ""

        try:
            df = pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False)
        except Exception as exc:
            raise ValidationDomainError(
                "CSV_PARSE_ERROR",
                f"Failed to parse CSV '{filename}': {exc}",
            ) from exc

        columns = [str(col).strip() for col in df.columns]
        header = f"File: {filename} | Rows: {len(df)} | Columns: {', '.join(columns)}"
        lines: list[str] = [header]

        for row_idx, (_, row) in enumerate(df.iterrows(), start=1):
            values = [str(val).strip() for val in row.tolist()]
            pairs = " | ".join(f"{col}: {val}" for col, val in zip(columns, values, strict=True))
            lines.append(f"Row {row_idx}: {pairs}")

        return "\n".join(lines)
