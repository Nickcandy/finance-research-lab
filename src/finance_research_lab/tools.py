from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent_models import ToolResult
from .models import AShareCompany, NewsTrace, RawNews, ResearchReport, WatchlistItem
from .news_fetcher import UrlOpen as FetchUrlOpen
from .news_fetcher import fetch_news
from .news_trace import (
    build_research_report,
    load_a_share_universe,
    load_watchlist,
    verify_research_report_candidates,
)
from .report import render_news_trace, render_research_report
from .research_agent import analyze_research_report_with_agent


def read_watchlist_tool(path: str | Path) -> ToolResult:
    """Read the local watchlist as an Agent tool."""

    try:
        items = load_watchlist(path)
    except Exception as exc:  # pragma: no cover - defensive boundary for CLI usage
        return ToolResult("read_watchlist", "error", [], str(exc))
    return ToolResult("read_watchlist", "success", items)


def read_a_share_universe_tool(path: str | Path) -> ToolResult:
    """Read the local A-share company universe as an Agent tool."""

    try:
        companies = load_a_share_universe(path)
    except Exception as exc:  # pragma: no cover - defensive boundary for CLI usage
        return ToolResult("read_a_share_universe", "error", [], str(exc))
    return ToolResult("read_a_share_universe", "success", companies)


def fetch_news_tool(url: str, *, urlopen: FetchUrlOpen | None = None) -> ToolResult:
    """Fetch one static HTML news article as trusted Agent input."""

    try:
        news = fetch_news(url, **({"urlopen": urlopen} if urlopen is not None else {}))
    except Exception as exc:  # pragma: no cover - defensive boundary for CLI usage
        return ToolResult("fetch_news", "error", None, str(exc))
    return ToolResult("fetch_news", "success", news)


def trace_news_tool(
    news: RawNews,
    watchlist: list[WatchlistItem],
    a_share_universe: list[AShareCompany] | None = None,
    **agent_kwargs: Any,
) -> ToolResult:
    """Convert a hot topic into a structured news trace."""

    try:
        trace = analyze_research_report_with_agent(
            news,
            watchlist,
            **agent_kwargs,
        )
    except Exception as agent_exc:
        try:
            trace = build_research_report(news, watchlist, a_share_universe)
        except Exception as fallback_exc:  # pragma: no cover - defensive boundary for CLI usage
            return ToolResult("trace_news", "error", None, str(fallback_exc))
        return ToolResult("trace_news", "success", trace, f"agent fallback: {agent_exc}")
    if a_share_universe is not None:
        trace = verify_research_report_candidates(trace, watchlist, a_share_universe)
    return ToolResult("trace_news", "success", trace)


def render_report_tool(trace: NewsTrace | ResearchReport) -> ToolResult:
    """Render a structured trace into Markdown."""

    try:
        if isinstance(trace, ResearchReport):
            markdown = render_research_report(trace)
        else:
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
