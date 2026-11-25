"""Current UTC date/time tool with optional ISO-8601 timezone offset."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from app.domain.value_objects.enums import ToolName

if TYPE_CHECKING:
    from collections.abc import Callable

_OFFSET_PATTERN = re.compile(r"^(?P<sign>[+-])(?P<hours>\d{2}):(?P<minutes>\d{2})$")


def _parse_timezone_offset(offset: str) -> timezone:
    """Parse 'Z' or '±HH:MM' into a fixed-offset timezone."""
    cleaned = offset.strip()
    if cleaned.upper() == "Z":
        return UTC

    match = _OFFSET_PATTERN.match(cleaned)
    if match is None:
        raise ValueError("Invalid timezone_offset. Expected 'Z' or '±HH:MM' (e.g. '+05:30').")

    hours = int(match.group("hours"))
    minutes = int(match.group("minutes"))
    if hours > 23 or minutes > 59:
        raise ValueError("timezone_offset hours must be 00-23 and minutes 00-59.")

    delta = timedelta(hours=hours, minutes=minutes)
    if match.group("sign") == "-":
        delta = -delta
    return timezone(delta)


class CurrentDateTool:
    """Returns current UTC date/time in ISO-8601 format, optionally converted to an offset."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))

    @property
    def name(self) -> ToolName:
        return ToolName.CURRENT_DATE

    @property
    def description(self) -> str:
        return (
            "Return the current date and time in ISO-8601 format (UTC by default, or "
            "converted to an optional ±HH:MM timezone offset)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "timezone_offset": {
                    "type": "string",
                    "description": "Optional UTC offset in '±HH:MM' format or 'Z'.",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> str:
        """Return ISO-8601 timestamp for the current clock time and optional offset."""
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        raw_offset = kwargs.get("timezone_offset")
        if raw_offset is None:
            return now.astimezone(UTC).isoformat()

        if not isinstance(raw_offset, str):
            raise ValueError("Argument 'timezone_offset' must be a string.")
        tz = _parse_timezone_offset(raw_offset)
        return now.astimezone(tz).isoformat()
