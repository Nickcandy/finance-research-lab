from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent_models import AgentRun, AgentStep, ToolResult
from .tools import read_watchlist_tool, render_report_tool, trace_news_tool, write_report_tool


def _summarize_output(output: Any) -> str:
    if isinstance(output, list):
        return f"{len(output)} item(s)"
    if output is None:
        return "none"
    text = str(output).replace("\n", " ")
    if len(text) > 160:
        return f"{text[:157]}..."
    return text


def _step(step_name: str, result: ToolResult) -> AgentStep:
    summary = result.error if result.status == "error" else _summarize_output(result.output)
    return AgentStep(
        step_name=step_name,
        tool_name=result.tool_name,
        status=result.status,
        summary=summary,
    )


def run_news_trace_workflow(
    headline: str,
    source: str,
    watchlist_path: str | Path,
    output_path: str | Path,
) -> AgentRun:
    """Run the deterministic v0 Agent workflow for one news trace.

    This is intentionally not a free-form autonomous loop yet. The workflow is
    code-controlled and observable: each tool call creates an AgentStep. Later,
    an LLM can be inserted between steps for classification, summarization, or
    report writing without changing the external CLI behavior.
    """

    steps: list[AgentStep] = []

    watchlist_result = read_watchlist_tool(watchlist_path)
    steps.append(_step("read_watchlist", watchlist_result))
    if watchlist_result.status == "error":
        return AgentRun("news_trace", steps, str(output_path))

    trace_result = trace_news_tool(headline, source, watchlist_result.output)
    steps.append(_step("trace_news", trace_result))
    if trace_result.status == "error":
        return AgentRun("news_trace", steps, str(output_path))

    render_result = render_report_tool(trace_result.output)
    steps.append(_step("render_report", render_result))
    if render_result.status == "error":
        return AgentRun("news_trace", steps, str(output_path))

    write_result = write_report_tool(render_result.output, output_path)
    steps.append(_step("write_report", write_result))

    return AgentRun("news_trace", steps, str(output_path))
