"""Tool registry and @lru_cache singleton factory."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from app.domain.exceptions import InvalidToolSelectionError
from app.infrastructure.tools.calculator import CalculatorTool
from app.infrastructure.tools.csv_lookup import CsvLookupTool
from app.infrastructure.tools.current_date import CurrentDateTool
from app.infrastructure.tools.weather_http import WeatherHttpTool

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.protocols.tool import AgentToolProtocol
    from app.domain.value_objects.enums import ToolName


class ToolRegistry:
    """Registry mapping ToolName identifiers to AgentToolProtocol instances."""

    def __init__(self, tools: Sequence[AgentToolProtocol] | None = None) -> None:
        default_tools: Sequence[AgentToolProtocol] = (
            tools
            if tools is not None
            else (
                CalculatorTool(),
                CurrentDateTool(),
                WeatherHttpTool(),
                CsvLookupTool(),
            )
        )
        self._tools: dict[ToolName, AgentToolProtocol] = {tool.name: tool for tool in default_tools}

    def get(self, name: ToolName) -> AgentToolProtocol:
        """Return the registered tool for `name` or raise InvalidToolSelectionError."""
        tool = self._tools.get(name)
        if tool is None:
            raise InvalidToolSelectionError(
                code="UNREGISTERED_TOOL",
                detail=f"Tool '{name}' is not registered in ToolRegistry.",
            )
        return tool

    def get_subset(self, selected_tools: Sequence[ToolName]) -> list[AgentToolProtocol]:
        """Return unique registered tools in the order requested by `selected_tools`."""
        return [self.get(name) for name in dict.fromkeys(selected_tools)]

    def list_tools(self) -> list[AgentToolProtocol]:
        """Return all registered tool instances."""
        return list(self._tools.values())

    def available_names(self) -> list[ToolName]:
        """Return all registered ToolName identifiers."""
        return list(self._tools.keys())


@lru_cache(maxsize=1)
def get_tool_registry() -> ToolRegistry:
    """Return the cached singleton ToolRegistry with all core tools."""
    return ToolRegistry()
