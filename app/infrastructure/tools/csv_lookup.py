"""In-memory CSV row lookup tool with column filters and keyword search."""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Any

from app.domain.value_objects.enums import ToolName

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class CsvLookupTool:
    """Queries registered CSV rows by exact column filters or case-insensitive keyword."""

    def __init__(self, rows: Sequence[Mapping[str, str]] | None = None) -> None:
        self._rows: list[dict[str, str]] = [dict(row) for row in rows] if rows else []

    @property
    def name(self) -> ToolName:
        return ToolName.CSV_LOOKUP

    @property
    def description(self) -> str:
        return (
            "Search registered CSV records by keyword query and/or exact column "
            "value filters, returning matching rows as JSON."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Case-insensitive keyword substring to match across columns.",
                },
                "filters": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Exact column-to-value filters (case-insensitive).",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Maximum number of rows to return (default 10).",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def register_rows(self, rows: Sequence[Mapping[str, str]]) -> None:
        """Replace registered rows with the provided sequence."""
        self._rows = [dict(row) for row in rows]

    def load_csv_text(self, csv_text: str) -> None:
        """Parse raw CSV text with headers and register its rows."""
        reader = csv.DictReader(io.StringIO(csv_text.strip()))
        self._rows = [{str(k): str(v) for k, v in row.items() if k is not None} for row in reader]

    async def execute(self, **kwargs: Any) -> str:
        """Filter registered CSV rows by `filters`, `query`, and `limit`."""
        query = kwargs.get("query")
        if query is not None and not isinstance(query, str):
            raise ValueError("Argument 'query' must be a string.")

        filters = kwargs.get("filters")
        if filters is not None and not isinstance(filters, dict):
            raise ValueError("Argument 'filters' must be a mapping of column to value.")

        limit = kwargs.get("limit", 10)
        if isinstance(limit, bool) or not isinstance(limit, int) or not (1 <= limit <= 100):
            raise ValueError("Argument 'limit' must be an integer between 1 and 100.")

        normalized_query = query.strip().lower() if query else None
        normalized_filters = (
            {str(k).lower(): str(v).strip().lower() for k, v in filters.items()} if filters else {}
        )

        matches: list[dict[str, str]] = []
        for row in self._rows:
            if not _row_matches(row, normalized_filters, normalized_query):
                continue
            matches.append(row)
            if len(matches) >= limit:
                break

        return json.dumps({"count": len(matches), "rows": matches})


def _row_matches(
    row: dict[str, str],
    filters: dict[str, str],
    query: str | None,
) -> bool:
    """Return True if a row satisfies all column filters and optional keyword query."""
    if filters:
        lowered_row = {k.lower(): v.strip().lower() for k, v in row.items()}
        for col, expected in filters.items():
            if lowered_row.get(col) != expected:
                return False

    if query:
        return any(query in val.lower() for val in row.values())

    return True
