from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .akshare_evidence import AkShareEvidenceProvider
from .baostock_market import BaoStockMarketProvider
from .daily_radar_report import render_daily_event_radar
from .daily_radar_snapshot import build_daily_radar_snapshot, write_daily_radar_snapshot
from .event_clustering import cluster_market_events, rank_hot_events
from .event_sources import SHANGHAI, ThsNewsSource
from .evidence_tool_agent import run_evidence_tool_calls
from .llm.chat_completions_client import ChatCompletionsClient
from .market_evidence import FallbackMarketProvider, MarketEvidenceProvider
from .agent_report import render_research_agent_report
from .agent_models import AgentRun, AgentStep, ToolResult
from .agents.tools import ToolRegistry, ToolSpec
from .evidence import (
    build_evidence_plan,
    classify_event,
    fetch_company_announcements,
    fetch_financial_reports,
    fetch_market_snapshot,
    score_value_chain_relevance,
)
from .models import (
    CompanyAnnouncement,
    Evidence,
    EvidencePlan,
    FinancialSnapshot,
    MarketSnapshot,
    NewsItem,
    ResearchAgentResult,
    ResearchReport,
    ResearchTask,
    WatchlistItem,
)
from .news_trace import verify_research_report_candidates
from .radar_report import render_opportunity_radar
from .research_planner import plan_research_tasks
from .research_agent import analyze_research_report_with_agent
from .tools import (
    fetch_news_tool,
    read_a_share_universe_tool,
    read_watchlist_tool,
    render_report_tool,
    trace_news_tool,
    write_report_tool,
)

DEFAULT_A_SHARE_UNIVERSE_PATH = "data/a_share_universe.example.csv"
MAX_DAILY_CANDIDATES_PER_EVENT = 3
MAX_EVENT_RESEARCH_BODY_CHARS = 12_000


def _summarize_output(output: Any) -> str:
    if isinstance(output, (list, tuple)):
        return f"{len(output)} item(s)"
    if output is None:
        return "none"
    text = str(output).replace("\n", " ")
    if len(text) > 160:
        return f"{text[:157]}..."
    return text


def _step(step_name: str, result: ToolResult) -> AgentStep:
    if result.status == "error":
        summary = result.error
    elif result.error:
        summary = f"{_summarize_output(result.output)}; {result.error}"
    else:
        summary = _summarize_output(result.output)
    return AgentStep(
        step_name=step_name,
        tool_name=result.tool_name,
        status=result.status,
        summary=summary,
    )


def run_news_trace_workflow(
    url: str,
    watchlist_path: str | Path,
    output_path: str | Path,
    a_share_universe_path: str | Path = DEFAULT_A_SHARE_UNIVERSE_PATH,
) -> AgentRun:
    """Run the deterministic v0 Agent workflow for one news trace.

    This is intentionally not a free-form autonomous loop yet. The workflow is
    code-controlled and observable: each tool call creates an AgentStep. Later,
    an LLM can be inserted between steps for classification, summarization, or
    report writing without changing the external CLI behavior.
    """

    steps: list[AgentStep] = []

    fetch_result = fetch_news_tool(url)
    steps.append(_step("fetch_news", fetch_result))
    if fetch_result.status == "error":
        return AgentRun("news_trace", steps, str(output_path))

    watchlist_result = read_watchlist_tool(watchlist_path)
    steps.append(_step("read_watchlist", watchlist_result))
    if watchlist_result.status == "error":
        return AgentRun("news_trace", steps, str(output_path))

    universe_result = read_a_share_universe_tool(a_share_universe_path)
    steps.append(_step("read_a_share_universe", universe_result))
    if universe_result.status == "error":
        return AgentRun("news_trace", steps, str(output_path))

    trace_result = trace_news_tool(
        fetch_result.output,
        watchlist_result.output,
        universe_result.output,
    )
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


def run_radar_workflow(
    urls: list[str],
    watchlist_path: str | Path,
    output_path: str | Path,
    a_share_universe_path: str | Path = DEFAULT_A_SHARE_UNIVERSE_PATH,
) -> AgentRun:
    """Run the deterministic radar workflow for multiple news URLs."""

    steps: list[AgentStep] = []
    reports: list[ResearchReport] = []

    watchlist_result = read_watchlist_tool(watchlist_path)
    steps.append(_step("read_watchlist", watchlist_result))
    if watchlist_result.status == "error":
        return AgentRun("radar", steps, str(output_path))

    universe_result = read_a_share_universe_tool(a_share_universe_path)
    steps.append(_step("read_a_share_universe", universe_result))
    if universe_result.status == "error":
        return AgentRun("radar", steps, str(output_path))

    for url in urls:
        fetch_result = fetch_news_tool(url)
        steps.append(_step("fetch_news", fetch_result))
        if fetch_result.status == "error":
            continue

        trace_result = trace_news_tool(
            fetch_result.output,
            watchlist_result.output,
            universe_result.output,
        )
        steps.append(_step("trace_news", trace_result))
        if trace_result.status == "error":
            continue
        reports.append(trace_result.output)

    if not reports:
        return AgentRun("radar", steps, str(output_path))

    try:
        markdown = render_opportunity_radar(reports)
    except Exception as exc:  # pragma: no cover - defensive boundary for CLI usage
        render_result = ToolResult("render_opportunity_radar", "error", "", str(exc))
    else:
        render_result = ToolResult("render_opportunity_radar", "success", markdown)
    steps.append(_step("render_radar_report", render_result))
    if render_result.status == "error":
        return AgentRun("radar", steps, str(output_path))

    write_result = write_report_tool(render_result.output, output_path)
    steps.append(_step("write_report", write_result))

    return AgentRun("radar", steps, str(output_path))


def run_daily_radar_workflow(
    output_path: str | Path,
    event_cache_path: str | Path = "data/event_cache/ths",
    as_of: datetime | None = None,
    *,
    watchlist_path: str | Path = "data/watchlist.example.csv",
    a_share_universe_path: str | Path = "data/a_share_universe.csv",
    evidence_cache_path: str | Path = "data/akshare_cache",
    market_cache_path: str | Path = "data/baostock_cache",
    refresh_evidence: bool = False,
    json_output_path: str | Path | None = None,
) -> AgentRun:
    """Discover, cluster, rank, and render the latest 24-hour market events."""

    steps: list[AgentStep] = []
    window_end = _shanghai_time(as_of or datetime.now(SHANGHAI))
    window_start = window_end - timedelta(hours=24)

    try:
        items = ThsNewsSource(event_cache_path).fetch(window_start, window_end)
    except Exception as exc:
        fetch_result = ToolResult("ths_global_news", "error", (), str(exc))
    else:
        fetch_result = ToolResult("ths_global_news", "success", items)
    steps.append(_step("fetch_event_source", fetch_result))
    if fetch_result.status == "error":
        return AgentRun("daily_radar", steps, str(output_path))

    try:
        events = cluster_market_events(fetch_result.output)
    except Exception as exc:
        cluster_result = ToolResult("cluster_market_events", "error", (), str(exc))
    else:
        cluster_result = ToolResult("cluster_market_events", "success", events)
    steps.append(_step("cluster_market_events", cluster_result))
    if cluster_result.status == "error":
        return AgentRun("daily_radar", steps, str(output_path))

    try:
        ranked_events = rank_hot_events(cluster_result.output)
    except Exception as exc:
        rank_result = ToolResult("rank_hot_events", "error", (), str(exc))
    else:
        if ranked_events:
            rank_result = ToolResult("rank_hot_events", "success", ranked_events)
        else:
            rank_result = ToolResult(
                "rank_hot_events", "error", (), "no market events found"
            )
    steps.append(_step("rank_hot_events", rank_result))
    if rank_result.status == "error":
        return AgentRun("daily_radar", steps, str(output_path))

    watchlist_result = read_watchlist_tool(watchlist_path)
    steps.append(_step("read_watchlist", watchlist_result))
    if watchlist_result.status == "error":
        return AgentRun("daily_radar", steps, str(output_path))

    universe_result = read_a_share_universe_tool(a_share_universe_path)
    steps.append(_step("read_a_share_universe", universe_result))
    if universe_result.status == "error":
        return AgentRun("daily_radar", steps, str(output_path))

    company_provider = AkShareEvidenceProvider(evidence_cache_path, refresh=refresh_evidence)
    market_provider = FallbackMarketProvider(
        BaoStockMarketProvider(market_cache_path, refresh=refresh_evidence),
        company_provider,
    )
    registry = _research_tool_registry(company_provider, market_provider)
    reports: list[ResearchReport | None] = []
    daily_tool_results: tuple[ToolResult, ...] = ()
    daily_attempted_tools: dict[str, frozenset[str]] = {}
    for index, event in enumerate(rank_result.output, start=1):
        news = _market_event_news(event)
        trace_result = trace_news_tool(
            news,
            watchlist_result.output,
            universe_result.output,
        )
        steps.append(_step(f"analyze_event:{index}", trace_result))
        if trace_result.status == "error":
            reports.append(None)
            continue

        candidate_symbols = tuple(
            dict.fromkeys(
                impact.symbol
                for impact in trace_result.output.stock_impacts
                if (
                    impact.market == "A股"
                    and impact.verification_status != "excluded"
                    and impact.impact_type in {"direct", "indirect", "negative"}
                    and impact.impact_strength in {"medium", "high"}
                )
            )
        )[:MAX_DAILY_CANDIDATES_PER_EVENT]
        daily_tool_results, evidence_warnings = _complete_candidate_evidence(
            registry,
            candidate_symbols,
            daily_tool_results,
            daily_attempted_tools,
            steps,
        )
        announcements, financials, markets = _evidence_outputs(daily_tool_results)
        report = _apply_tool_verification(
            trace_result.output,
            announcements,
            financials,
            markets,
        )
        verify_result = ToolResult(
            "verify_event_candidates",
            "success",
            report,
            "；".join(evidence_warnings),
        )
        steps.append(_step(f"verify_event_candidates:{index}", verify_result))
        reports.append(report)

    if not any(report is not None for report in reports):
        return AgentRun("daily_radar", steps, str(output_path))

    try:
        markdown = render_daily_event_radar(
            rank_result.output,
            window_start,
            window_end,
            tuple(reports),
        )
    except Exception as exc:
        render_result = ToolResult("render_daily_event_radar", "error", "", str(exc))
    else:
        render_result = ToolResult("render_daily_event_radar", "success", markdown)
    steps.append(_step("render_daily_radar", render_result))
    if render_result.status == "error":
        return AgentRun("daily_radar", steps, str(output_path))

    write_result = write_report_tool(render_result.output, output_path)
    steps.append(_step("write_report", write_result))
    if write_result.status == "error" or json_output_path is None:
        return AgentRun("daily_radar", steps, str(output_path))

    try:
        snapshot = build_daily_radar_snapshot(
            rank_result.output,
            reports,
            steps,
            window_start,
            window_end,
            generated_at=window_end,
        )
        snapshot_path = write_daily_radar_snapshot(snapshot, json_output_path)
    except Exception as exc:
        snapshot_result = ToolResult("write_daily_radar_snapshot", "error", "", str(exc))
    else:
        snapshot_result = ToolResult(
            "write_daily_radar_snapshot", "success", str(snapshot_path)
        )
    steps.append(_step("write_snapshot", snapshot_result))
    return AgentRun("daily_radar", steps, str(output_path))


def _shanghai_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI)
    return value.astimezone(SHANGHAI)


def _market_event_news(event) -> NewsItem:
    sources = tuple(dict.fromkeys(item.source for item in event.items if item.source))
    body_parts = []
    for item in event.items:
        body_parts.append(
            f"来源：{item.source or '未提供'}\n标题：{item.headline}\n"
            f"URL：{item.url or '未提供'}\n正文：{item.body or '未提供'}"
        )
    body = "\n\n".join(body_parts)
    if len(body) > MAX_EVENT_RESEARCH_BODY_CHARS:
        body = f"{body[: MAX_EVENT_RESEARCH_BODY_CHARS - 3]}..."
    latest = event.items[0]
    return NewsItem(
        headline=event.title,
        source=" / ".join(sources) or "未提供",
        url=event.source_urls[0] if event.source_urls else "",
        published_at=latest.published_at,
        body=body,
        source_type=latest.source_type,
    )


def run_research_agent_workflow(
    url: str,
    watchlist_path: str | Path,
    output_path: str | Path,
    a_share_universe_path: str | Path = DEFAULT_A_SHARE_UNIVERSE_PATH,
    evidence_cache_path: str | Path = "data/akshare_cache",
    market_cache_path: str | Path = "data/baostock_cache",
    refresh_evidence: bool = False,
) -> AgentRun:
    """Run the minimal code-controlled AI research Agent workflow."""

    company_provider = AkShareEvidenceProvider(evidence_cache_path, refresh=refresh_evidence)
    market_provider = FallbackMarketProvider(
        BaoStockMarketProvider(market_cache_path, refresh=refresh_evidence),
        company_provider,
    )
    registry = _research_tool_registry(company_provider, market_provider)
    steps: list[AgentStep] = []

    fetch_result = registry.execute("fetch_news", {"url": url})
    steps.append(_step("fetch_news", fetch_result))
    if fetch_result.status == "error":
        return AgentRun("research_agent", steps, str(output_path))

    watchlist_result = registry.execute("read_watchlist", {"path": watchlist_path})
    steps.append(_step("read_watchlist", watchlist_result))
    if watchlist_result.status == "error":
        return AgentRun("research_agent", steps, str(output_path))

    universe_result = read_a_share_universe_tool(a_share_universe_path)
    steps.append(_step("read_a_share_universe", universe_result))
    if universe_result.status == "error":
        return AgentRun("research_agent", steps, str(output_path))

    classification = classify_event(fetch_result.output, watchlist_result.output)
    classify_result = ToolResult("classify_event", "success", classification)
    steps.append(_step("classify_event", classify_result))

    tasks = plan_research_tasks(fetch_result.output, watchlist_result.output)
    plan_result = ToolResult("plan_research_tasks", "success", tasks)
    steps.append(_step("plan_research_tasks", plan_result))

    trace_result = registry.execute(
        "trace_news",
        {
            "news": fetch_result.output,
            "watchlist": watchlist_result.output,
            "a_share_universe": universe_result.output,
        },
    )
    steps.append(_step("trace_news", trace_result))
    if trace_result.status == "error":
        return AgentRun("research_agent", steps, str(output_path))

    candidate_symbols = tuple(
        dict.fromkeys(impact.symbol for impact in trace_result.output.stock_impacts if impact.market == "A股")
    )
    tool_results: tuple[ToolResult, ...] = ()
    try:
        if trace_result.error:
            raise RuntimeError(trace_result.error)
        outcome = run_evidence_tool_calls(
            ChatCompletionsClient(), registry, fetch_result.output, trace_result.output
        )
        tool_result = ToolResult("plan_evidence_tool_calls", "success", outcome.results)
        steps.append(_step("plan_evidence_tool_calls", tool_result))
        tool_results, completion_warnings = _complete_candidate_evidence(
            registry,
            candidate_symbols,
            outcome.results,
            outcome.attempted_tools,
            steps,
        )
        company_announcements, financial_snapshots, market_snapshots = _evidence_outputs(tool_results)
        evidence_warnings = [*outcome.warnings, *completion_warnings]
        evidence_plan = EvidencePlan(
            event_type=classification.event_type,
            candidate_symbols=candidate_symbols,
            required_tools=tuple(dict.fromkeys(result.tool_name for result in tool_results)),
            questions=tuple(task.question for task in tasks),
        )
    except Exception as exc:
        evidence_warnings = [f"tool calling fallback：{exc}"]
        evidence_plan = build_evidence_plan(classification, candidate_symbols)
        evidence_plan_result = ToolResult("build_evidence_plan", "success", evidence_plan, str(exc))
        steps.append(_step("build_evidence_plan", evidence_plan_result))
        company_announcements, financial_snapshots, fallback_warnings = _collect_company_evidence(
            registry, evidence_plan, steps
        )
        market_snapshots, market_warnings = _collect_market_evidence(registry, evidence_plan, steps)
        evidence_warnings.extend(fallback_warnings)
        evidence_warnings.extend(market_warnings)

    final_report = trace_result.output
    if tool_results:
        try:
            final_report = analyze_research_report_with_agent(
                fetch_result.output,
                watchlist_result.output,
                evidence_context=[_tool_context(result) for result in tool_results],
            )
        except Exception as exc:
            evidence_warnings.append(f"evidence synthesis fallback：{exc}")
    final_report = verify_research_report_candidates(
        final_report, watchlist_result.output, universe_result.output
    )
    final_report = _apply_tool_verification(
        final_report,
        company_announcements,
        financial_snapshots,
        market_snapshots,
    )
    trace_result = ToolResult("synthesize_evidence_report", "success", final_report)
    steps.append(_step("synthesize_evidence_report", trace_result))

    value_chain_scores = tuple(
        score_value_chain_relevance(fetch_result.output, item)
        for item in watchlist_result.output
        if item.symbol in evidence_plan.candidate_symbols
    )
    scale_result = ToolResult("score_value_chain", "success", value_chain_scores)
    steps.append(_step("score_value_chain", scale_result))

    evidence = _collect_evidence(
        news=fetch_result.output,
        watchlist=watchlist_result.output,
        report=trace_result.output,
        tasks=tasks,
        evidence_plan=evidence_plan,
        company_announcements=company_announcements,
        financial_snapshots=financial_snapshots,
        market_snapshots=market_snapshots,
    )
    evidence_result = ToolResult("collect_evidence", "success", evidence)
    steps.append(_step("collect_evidence", evidence_result))

    result = ResearchAgentResult(
        tasks=tasks,
        evidence=evidence,
        report=trace_result.output,
        classification=classification,
        evidence_plan=evidence_plan,
        company_announcements=company_announcements,
        financial_snapshots=financial_snapshots,
        market_snapshots=market_snapshots,
        value_chain_scores=value_chain_scores,
        evidence_warnings=tuple(evidence_warnings),
    )
    markdown = render_research_agent_report(result, steps)
    render_result = ToolResult("render_research_agent_report", "success", markdown)
    steps.append(_step("render_agent_report", render_result))

    write_result = write_report_tool(render_result.output, output_path)
    steps.append(_step("write_report", write_result))

    return AgentRun("research_agent", steps, str(output_path))


def _evidence_outputs(
    results: tuple[ToolResult, ...],
) -> tuple[tuple[CompanyAnnouncement, ...], tuple[FinancialSnapshot, ...], tuple[MarketSnapshot, ...]]:
    announcements: list[CompanyAnnouncement] = []
    financials: list[FinancialSnapshot] = []
    markets: list[MarketSnapshot] = []
    for result in results:
        if result.status != "success":
            continue
        if result.tool_name == "fetch_company_announcements":
            announcements.extend(result.output)
        elif result.tool_name == "fetch_financial_reports":
            financials.extend(result.output)
        elif result.tool_name == "fetch_market_snapshot":
            markets.append(result.output)
    return tuple(announcements), tuple(financials), tuple(markets)


def _tool_context(result: ToolResult) -> dict[str, Any]:
    return {"tool": result.tool_name, "status": result.status, "output": str(result.output), "error": result.error}


def _apply_tool_verification(
    report: ResearchReport,
    announcements: tuple[CompanyAnnouncement, ...],
    financials: tuple[FinancialSnapshot, ...],
    markets: tuple[MarketSnapshot, ...],
) -> ResearchReport:
    company_symbols = {item.symbol for item in (*announcements, *financials)}
    market_by_symbol = {item.symbol: item for item in markets}
    impacts = []
    for impact in report.stock_impacts:
        if impact.verification_status == "excluded" or impact.impact_type == "false_positive":
            impacts.append(
                replace(impact, verification_status="excluded", verification_source="")
            )
        elif (
            impact.market == "A股"
            and impact.impact_type in {"direct", "indirect", "negative"}
            and impact.impact_strength in {"medium", "high"}
            and impact.symbol in company_symbols
            and impact.symbol in market_by_symbol
        ):
            market = market_by_symbol[impact.symbol]
            market_source = f"{market.provider} market" if market.provider else "market"
            impacts.append(
                replace(
                    impact,
                    verification_status="verified",
                    verification_source=f"AkShare company and {market_source} evidence",
                )
            )
        else:
            impacts.append(replace(impact, verification_status="unverified", verification_source=""))
    return replace(report, stock_impacts=tuple(impacts))


def _complete_candidate_evidence(
    registry: ToolRegistry,
    candidate_symbols: tuple[str, ...],
    initial_results: tuple[ToolResult, ...],
    attempted_tools: dict[str, frozenset[str]],
    steps: list[AgentStep],
) -> tuple[tuple[ToolResult, ...], list[str]]:
    results = list(initial_results)
    attempts = {symbol: set(names) for symbol, names in attempted_tools.items()}
    warnings: list[str] = []

    for symbol in candidate_symbols:
        coverage = _candidate_evidence_coverage(tuple(results)).get(symbol, set())
        if not coverage.intersection({"fetch_company_announcements", "fetch_financial_reports"}):
            for tool_name, arguments in (
                ("fetch_financial_reports", {"symbol": symbol}),
                ("fetch_company_announcements", {"symbol": symbol}),
            ):
                if tool_name in attempts.get(symbol, set()):
                    continue
                result = registry.execute(tool_name, arguments)
                results.append(result)
                attempts.setdefault(symbol, set()).add(tool_name)
                steps.append(_step(f"{tool_name}:{symbol}", result))
                if result.status == "error":
                    warnings.append(f"{symbol} {tool_name} 不可用：{result.error}")
                if symbol in _candidate_evidence_coverage((result,)):
                    break

        coverage = _candidate_evidence_coverage(tuple(results)).get(symbol, set())
        if "fetch_market_snapshot" not in coverage and "fetch_market_snapshot" not in attempts.get(symbol, set()):
            result = registry.execute("fetch_market_snapshot", {"symbol": symbol, "lookback_days": 5})
            results.append(result)
            attempts.setdefault(symbol, set()).add("fetch_market_snapshot")
            steps.append(_step(f"fetch_market_snapshot:{symbol}", result))
            if result.status == "error":
                warnings.append(f"{symbol} fetch_market_snapshot 不可用：{result.error}")

        coverage = _candidate_evidence_coverage(tuple(results)).get(symbol, set())
        if not coverage.intersection({"fetch_company_announcements", "fetch_financial_reports"}):
            warnings.append(f"{symbol} 缺少非空公司公告或财报证据。")
        if "fetch_market_snapshot" not in coverage:
            warnings.append(f"{symbol} 缺少有效行情证据。")

    attempted_tools.clear()
    attempted_tools.update({symbol: frozenset(names) for symbol, names in attempts.items()})
    return tuple(results), warnings


def _candidate_evidence_coverage(results: tuple[ToolResult, ...]) -> dict[str, set[str]]:
    coverage: dict[str, set[str]] = {}
    for result in results:
        if result.status != "success":
            continue
        output = result.output
        items = output if isinstance(output, tuple) else (output,)
        for item in items:
            symbol = getattr(item, "symbol", "")
            if symbol:
                coverage.setdefault(symbol, set()).add(result.tool_name)
    return coverage


def _research_tool_registry(
    company_provider: AkShareEvidenceProvider | None = None,
    market_provider: MarketEvidenceProvider | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="fetch_news",
            description="Fetch one static HTML news article.",
            parameters={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
            handler=fetch_news_tool,
        )
    )
    registry.register(
        ToolSpec(
            name="read_watchlist",
            description="Read local CSV watchlist.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=read_watchlist_tool,
        )
    )
    registry.register(
        ToolSpec(
            name="read_a_share_universe",
            description="Read local A-share company universe.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=read_a_share_universe_tool,
        )
    )
    registry.register(
        ToolSpec(
            name="trace_news",
            description="Convert news, watchlist, and A-share universe into a ResearchReport.",
            parameters={
                "type": "object",
                "properties": {
                    "news": {"type": "object"},
                    "watchlist": {"type": "array"},
                    "a_share_universe": {"type": "array"},
                },
                "required": ["news", "watchlist", "a_share_universe"],
            },
            handler=trace_news_tool,
        )
    )
    registry.register(
        ToolSpec(
            name="fetch_company_announcements",
            description="Fetch company announcement summaries.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
                "required": ["symbol"],
            },
            handler=lambda symbol, start_date="", end_date="": fetch_company_announcements(
                symbol, start_date, end_date, company_provider
            ),
        )
    )
    registry.register(
        ToolSpec(
            name="fetch_financial_reports",
            description="Fetch company financial report summary.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                },
                "required": ["symbol"],
            },
            handler=lambda symbol: fetch_financial_reports(symbol, (), company_provider),
        )
    )
    registry.register(
        ToolSpec(
            name="fetch_market_snapshot",
            description="Fetch recent price and volume snapshot.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "lookback_days": {"type": "integer"},
                },
                "required": ["symbol"],
            },
            handler=lambda symbol, lookback_days=5: fetch_market_snapshot(
                symbol, lookback_days, market_provider or company_provider
            ),
        )
    )
    return registry


def _collect_company_evidence(
    registry: ToolRegistry,
    plan: EvidencePlan,
    steps: list[AgentStep],
) -> tuple[tuple[CompanyAnnouncement, ...], tuple[FinancialSnapshot, ...], list[str]]:
    announcements: list[CompanyAnnouncement] = []
    financials: list[FinancialSnapshot] = []
    warnings: list[str] = []
    for symbol in plan.candidate_symbols:
        if "company_announcements" in plan.required_tools:
            result = registry.execute(
                "fetch_company_announcements", {"symbol": symbol, "start_date": "", "end_date": ""}
            )
            steps.append(_step(f"fetch_company_announcements:{symbol}", result))
            if result.status == "success":
                announcements.extend(result.output)
            else:
                warnings.append(f"{symbol} 公告证据不可用：{result.error}")
        if "financial_reports" in plan.required_tools:
            result = registry.execute("fetch_financial_reports", {"symbol": symbol})
            steps.append(_step(f"fetch_financial_reports:{symbol}", result))
            if result.status == "success":
                financials.extend(result.output)
            else:
                warnings.append(f"{symbol} 财报证据不可用：{result.error}")
    return tuple(announcements), tuple(financials), warnings


def _collect_market_evidence(
    registry: ToolRegistry,
    plan: EvidencePlan,
    steps: list[AgentStep],
) -> tuple[tuple[MarketSnapshot, ...], list[str]]:
    if "market_snapshot" not in plan.required_tools:
        return (), []
    snapshots: list[MarketSnapshot] = []
    warnings: list[str] = []
    for symbol in plan.candidate_symbols:
        result = registry.execute("fetch_market_snapshot", {"symbol": symbol, "lookback_days": 5})
        steps.append(_step(f"fetch_market_snapshot:{symbol}", result))
        if result.status == "success":
            snapshots.append(result.output)
        else:
            warnings.append(f"{symbol} 行情证据不可用：{result.error}")
    return tuple(snapshots), warnings


def _collect_evidence(
    *,
    news: NewsItem,
    watchlist: list[WatchlistItem],
    report: ResearchReport,
    tasks: tuple[ResearchTask, ...],
    evidence_plan: EvidencePlan | None = None,
    company_announcements: tuple[CompanyAnnouncement, ...] = (),
    financial_snapshots: tuple[FinancialSnapshot, ...] = (),
    market_snapshots: tuple[MarketSnapshot, ...] = (),
) -> tuple[Evidence, ...]:
    task_questions = tuple(task.question for task in tasks)
    evidence: list[Evidence] = [
        Evidence(
            source_type="news",
            title=news.headline,
            url=news.url,
            summary=f"来源：{news.source or '未提供'}；发布时间：{news.published_at or '未提供'}",
            supports=task_questions[:2],
        )
    ]

    watchlist_by_symbol = {item.symbol: item for item in watchlist}
    for impact in report.stock_impacts:
        item = watchlist_by_symbol.get(impact.symbol)
        if item is not None:
            evidence.append(
                Evidence(
                    source_type="watchlist",
                    title=f"{item.name}（{item.symbol}）股票池记录",
                    url="",
                    summary=(
                        f"股票池主题：{' / '.join(item.themes) or '未标注主题'}；"
                        f"关注逻辑：{item.thesis or '未提供'}；风险：{item.risks or '未提供'}"
                    ),
                    supports=(tasks[2].question,) if len(tasks) > 2 else task_questions,
                )
            )
        for item_evidence in impact.evidence:
            evidence.append(
                Evidence(
                    source_type="stock_impact",
                    title=f"{impact.name}（{impact.symbol}）影响证据",
                    url=news.url,
                    summary=item_evidence,
                    supports=(impact.reasoning,) if impact.reasoning else task_questions,
                )
            )
    if evidence_plan is not None:
        evidence.append(
            Evidence(
                source_type="agent",
                title=f"{evidence_plan.event_type} 证据计划",
                url="",
                summary=(
                    f"候选标的：{', '.join(evidence_plan.candidate_symbols) or '待补充'}；"
                    f"工具：{', '.join(evidence_plan.required_tools) or '待补充'}"
                ),
                supports=evidence_plan.questions,
            )
        )
    for announcement in company_announcements:
        evidence.append(
            Evidence(
                source_type="company_announcement",
                title=announcement.title,
                url=announcement.url,
                summary=(
                    f"公告日期：{announcement.published_at or '未提供'}；"
                    f"来源：{announcement.provider or '未提供'}"
                ),
                supports=(announcement.symbol,),
            )
        )
    for financial in financial_snapshots:
        evidence.append(
            Evidence(
                source_type="financial_report",
                title=f"{financial.symbol} {financial.report_period} 财报摘要",
                url="",
                summary=(
                    f"收入：{_format_optional_number(financial.revenue)}；"
                    f"收入同比：{_format_optional_number(financial.revenue_yoy)}%；"
                    f"净利润：{_format_optional_number(financial.net_profit)}；"
                    f"经营现金流：{_format_optional_number(financial.operating_cash_flow)}；"
                    f"来源：{financial.provider or '未提供'}"
                ),
                supports=(financial.symbol,),
            )
        )
    for snapshot in market_snapshots:
        evidence.append(
            Evidence(
                source_type="market_snapshot",
                title=f"{snapshot.symbol} 最近 {snapshot.lookback_days} 日行情",
                url="",
                summary=(
                    f"收盘：{snapshot.close}；区间涨跌幅："
                    f"{_format_optional_number(snapshot.period_return_pct)}%；"
                    f"成交量：{snapshot.volume}；成交额：{snapshot.amount}；"
                    f"来源：{snapshot.provider or '未提供'}"
                ),
                supports=(snapshot.symbol,),
            )
        )
    return tuple(evidence)


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return "待补充"
    return f"{value:g}"
