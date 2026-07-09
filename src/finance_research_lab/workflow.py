from __future__ import annotations

from pathlib import Path
from typing import Any

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
    RawNews,
    ResearchAgentResult,
    ResearchReport,
    ResearchTask,
    WatchlistItem,
)
from .radar_report import render_opportunity_radar
from .research_planner import plan_research_tasks
from .tools import (
    fetch_news_tool,
    read_a_share_universe_tool,
    read_watchlist_tool,
    render_report_tool,
    trace_news_tool,
    write_report_tool,
)

DEFAULT_A_SHARE_UNIVERSE_PATH = "data/a_share_universe.example.csv"


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


def run_research_agent_workflow(
    url: str,
    watchlist_path: str | Path,
    output_path: str | Path,
    a_share_universe_path: str | Path = DEFAULT_A_SHARE_UNIVERSE_PATH,
) -> AgentRun:
    """Run the minimal code-controlled AI research Agent workflow."""

    registry = _research_tool_registry()
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

    evidence_plan = build_evidence_plan(classification)
    evidence_plan_result = ToolResult("build_evidence_plan", "success", evidence_plan)
    steps.append(_step("build_evidence_plan", evidence_plan_result))

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

    company_announcements, financial_snapshots = _collect_company_evidence(evidence_plan)
    company_evidence_result = ToolResult(
        "fetch_company_evidence",
        "success",
        {
            "announcements": company_announcements,
            "financials": financial_snapshots,
        },
    )
    steps.append(_step("fetch_company_evidence", company_evidence_result))

    market_snapshots = _collect_market_evidence(evidence_plan)
    market_evidence_result = ToolResult("fetch_market_evidence", "success", market_snapshots)
    steps.append(_step("fetch_market_evidence", market_evidence_result))

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
    )
    markdown = render_research_agent_report(result, steps)
    render_result = ToolResult("render_research_agent_report", "success", markdown)
    steps.append(_step("render_agent_report", render_result))

    write_result = write_report_tool(render_result.output, output_path)
    steps.append(_step("write_report", write_result))

    return AgentRun("research_agent", steps, str(output_path))


def _research_tool_registry() -> ToolRegistry:
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
                "required": ["symbol", "start_date", "end_date"],
            },
            handler=fetch_company_announcements,
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
                    "periods": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["symbol", "periods"],
            },
            handler=fetch_financial_reports,
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
                "required": ["symbol", "lookback_days"],
            },
            handler=fetch_market_snapshot,
        )
    )
    return registry


def _collect_company_evidence(
    plan: EvidencePlan,
) -> tuple[tuple[CompanyAnnouncement, ...], tuple[FinancialSnapshot, ...]]:
    announcements: list[CompanyAnnouncement] = []
    financials: list[FinancialSnapshot] = []
    for symbol in plan.candidate_symbols:
        if "company_announcements" in plan.required_tools:
            announcements.extend(fetch_company_announcements(symbol, "", ""))
        if "financial_reports" in plan.required_tools:
            financials.extend(fetch_financial_reports(symbol, ("latest",)))
    return tuple(announcements), tuple(financials)


def _collect_market_evidence(plan: EvidencePlan) -> tuple[MarketSnapshot, ...]:
    if "market_snapshot" not in plan.required_tools:
        return ()
    return tuple(fetch_market_snapshot(symbol, 5) for symbol in plan.candidate_symbols)


def _collect_evidence(
    *,
    news: RawNews,
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
                summary=announcement.summary or "待补充",
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
                    f"净利润：{_format_optional_number(financial.net_profit)}"
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
                    f"收盘：{snapshot.close}；涨跌幅：{snapshot.pct_chg}%；"
                    f"成交量：{snapshot.volume}；成交额：{snapshot.amount}"
                ),
                supports=(snapshot.symbol,),
            )
        )
    return tuple(evidence)


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return "待补充"
    return f"{value:g}"
