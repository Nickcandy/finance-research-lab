from __future__ import annotations

from pathlib import Path

from .agent_models import ToolResult
from .models import NewsTrace, WatchlistItem
from .news_trace import build_trace, load_watchlist
from .report import render_news_trace


def read_watchlist_tool(path: str | Path) -> ToolResult:
    """Read the local watchlist as an Agent tool."""

    try:
        items = load_watchlist(path)
    except Exception as exc:  # pragma: no cover - defensive boundary for CLI usage
        return ToolResult("read_watchlist", "error", [], str(exc))
    return ToolResult("read_watchlist", "success", items)


def trace_news_tool(headline: str, source: str, watchlist: list[WatchlistItem]) -> ToolResult:
    """Convert a hot topic into a structured news trace."""

    try:
        trace = build_trace(headline, source, watchlist)
    except Exception as exc:  # pragma: no cover - defensive boundary for CLI usage
        return ToolResult("trace_news", "error", None, str(exc))
    return ToolResult("trace_news", "success", trace)


def render_report_tool(trace: NewsTrace) -> ToolResult:
    """Render a structured trace into Markdown."""

    try:
        markdown = render_news_trace(trace)
    except Exception as exc:  # pragma: no cover - defensive boundary for CLI usage
        return ToolResult("render_report", "error", "", str(exc))
    return ToolResult("render_report", "success", markdown)


def write_report_tool(markdown: str, output: str | Path) -> ToolResult:
    """Persist a Markdown report."""

    try:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    except Exception as exc:  # pragma: no cover - defensive boundary for CLI usage
        return ToolResult("write_report", "error", str(output), str(exc))
    return ToolResult("write_report", "success", str(output_path))
