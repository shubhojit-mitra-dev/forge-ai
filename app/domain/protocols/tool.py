"""Agent tool protocol definition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.domain.value_objects.enums import ToolName


@runtime_checkable
class AgentToolProtocol(Protocol):
    """Port for deterministic or external tools attachable to generated agents."""

    @property
    def name(self) -> ToolName:
        """Unique registered tool identifier."""
        ...

    @property
    def description(self) -> str:
        """Human- and LLM-readable description of what the tool does."""
        ...

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """JSON Schema describing accepted keyword arguments."""
        ...

    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool with validated keyword arguments and return text."""
        ...
