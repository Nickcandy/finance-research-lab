from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


ToolStatus = Literal["success", "error"]


@dataclass(frozen=True)
class ToolResult:
    """Structured result for an Agent tool call.

    The project currently runs a deterministic local workflow. Keeping tool
    results explicit makes it easy to later replace deterministic steps with
    LLM function-calling while preserving logs and tests.
    """

    tool_name: str
    status: ToolStatus
    output: Any
    error: str = ""


@dataclass(frozen=True)
class AgentStep:
    """One observable step in an Agent run."""

    step_name: str
    tool_name: str
    status: ToolStatus
    summary: str


@dataclass(frozen=True)
class AgentRun:
    """Execution record for one research workflow run."""

    run_name: str
    steps: list[AgentStep]
    output_path: str
