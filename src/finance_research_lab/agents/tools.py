from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from finance_research_lab.agent_models import ToolResult


@dataclass(frozen=True)
class ToolSpec:
    """Schema plus handler for one callable Agent tool."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Small registry that keeps tool schemas separate from business logic."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self.get(name)
        try:
            output = tool.handler(**arguments)
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ToolResult(name, "error", None, str(exc))
        if isinstance(output, ToolResult):
            return output
        return ToolResult(name, "success", output)

    def to_openai_tools(self) -> list[dict[str, Any]]:
        return [tool.to_openai_tool() for tool in self._tools.values()]
