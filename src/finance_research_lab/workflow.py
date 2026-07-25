from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .analysis_router import AnalysisRoute, AnalysisRouter
from .akshare_evidence import AkShareEvidenceProvider
from .baostock_market import BaoStockMarketProvider
from .claim_pipeline import ClaimPipeline
from .claims import Claim
from .daily_radar_report import render_daily_event_radar
from .daily_radar_snapshot import (
    build_daily_radar_snapshot,
    market_event_id,
    write_daily_radar_snapshot,
)
from .event_clustering import cluster_market_events, rank_hot_events
from .event_eligibility import is_market_event_researchable
from .event_catalog import event_catalog_path, write_event_catalog
from .event_analysis import event_analysis_path, write_successful_event_analysis
from .event_brief import EventBrief, build_event_brief
from .event_sources import SHANGHAI, ThsNewsSource
from .evidence_ledger import EvidenceLedger, build_evidence_ledgers
from .evidence_tool_agent import run_evidence_tool_calls
from .impact_assessment import ImpactAssessment
from .impact_features import build_impact_assessments
from .llm.chat_completions_client import ChatCompletionsClient
from .llm.usage import render_usage_markdown
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
    AShareCompany,
    Evidence,
    EvidencePlan,
    EventAnalysis,
    FinancialSnapshot,
    MarketSnapshot,
    MarketEvent,
    NewsItem,
    ResearchAgentResult,
    ResearchReport,
    ResearchTask,
    StockImpact,
    ValueChainTrace,
    WatchlistItem,
)
from .news_trace import verify_research_report_candidates
from .point_in_time import (
    build_point_in_time_payload,
    point_in_time_path,
    write_point_in_time,
)
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


@dataclass(frozen=True)
class MarketEventAnalysisOutcome:
    report: ResearchReport
    steps: tuple[AgentStep, ...]
    warnings: tuple[str, ...]
    assessments: tuple[ImpactAssessment, ...]


@dataclass(frozen=True)
class RoutedEventAnalysis:
    event: MarketEvent
    route: AnalysisRoute
    assessments: tuple[ImpactAssessment, ...]
    ledgers: tuple[EvidenceLedger, ...]
    brief: EventBrief
    report: ResearchReport | None
    fallback: str = ""
    warnings: tuple[str, ...] = ()


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
        warnings=(result.error,) if result.status == "success" and result.error else (),
    )


def run_news_trace_workflow(
    url: str,
    watchlist_path: str | Path,
    output_path: str | Path,
    a_share_universe_path: str | Path = DEFAULT_A_SHARE_UNIVERSE_PATH,
    *,
    llm_client: ChatCompletionsClient | None = None,
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
        **({"client": llm_client} if llm_client is not None else {}),
    )
    steps.append(_step("trace_news", trace_result))
    if trace_result.status == "error":
        return AgentRun("news_trace", steps, str(output_path))

    render_result = render_report_tool(trace_result.output)
    if render_result.status == "success":
        render_result = replace(
            render_result,
            output=_append_llm_usage(render_result.output, llm_client),
        )
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
    *,
    llm_client: ChatCompletionsClient | None = None,
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
            **({"client": llm_client} if llm_client is not None else {}),
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
        render_result = ToolResult(
            "render_opportunity_radar",
            "success",
            _append_llm_usage(markdown, llm_client),
        )
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
    llm_client: ChatCompletionsClient | None = None,
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
        all_ranked_events = (
            rank_hot_events(cluster_result.output, limit=len(cluster_result.output))
            if cluster_result.output
            else ()
        )
        ranked_events = tuple(
            event for event in all_ranked_events if is_market_event_researchable(event)
        )
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

    try:
        claim_result = ClaimPipeline(
            llm_client,
            Path(evidence_cache_path) / "claims",
        ).extract(ranked_events)
        ledgers = build_evidence_ledgers(
            ranked_events,
            claim_result.claims,
            universe_result.output,
            watchlist_symbols=(item.symbol for item in watchlist_result.output),
        )
        assessments = build_impact_assessments(
            ranked_events,
            ledgers,
            universe_result.output,
        )
    except Exception as exc:
        claim_step_result = ToolResult(
            "score_all_market_events",
            "error",
            (),
            str(exc),
        )
    else:
        claim_step_result = ToolResult(
            "score_all_market_events",
            "success",
            assessments,
            "；".join(
                warning
                for warning in claim_result.warnings
                if warning.startswith("claim cache ")
            ),
        )
    steps.append(_step("score_all_market_events", claim_step_result))
    if claim_step_result.status == "error":
        return AgentRun("daily_radar", steps, str(output_path))

    ledgers_by_event = _group_ledgers_by_event(ledgers)
    assessments_by_event = _group_assessments_by_event(assessments)
    claims_by_event = _group_claims_by_event(claim_result.claims)
    router = AnalysisRouter()
    company_provider = AkShareEvidenceProvider(evidence_cache_path, refresh=refresh_evidence)
    market_provider = FallbackMarketProvider(
        BaoStockMarketProvider(market_cache_path, refresh=refresh_evidence),
        company_provider,
    )
    registry = _research_tool_registry(company_provider, market_provider)
    reports: list[ResearchReport | None] = []
    routed_analyses: list[RoutedEventAnalysis] = []
    daily_tool_results: tuple[ToolResult, ...] = ()
    daily_attempted_tools: dict[str, frozenset[str]] = {}
    for index, event in enumerate(rank_result.output, start=1):
        event_id = market_event_id(event)
        event_assessments = assessments_by_event.get(event_id, ())
        route = _event_route(router, event_id, event_assessments)
        steps.append(
            _step(
                f"route_event:{index}",
                ToolResult(
                    "route_event_analysis",
                    "success",
                    "；".join((route.analysis_tier, *route.reason_codes)),
                ),
            )
        )
        fallback = ""
        warnings: tuple[str, ...] = ()
        event_ledgers = ledgers_by_event.get(event_id, ())
        event_claims = claims_by_event.get(event_id, ())
        brief = build_event_brief(
            event,
            event_claims,
            event_ledgers,
            event_assessments,
            universe_result.output,
        )
        if route.analysis_tier == "pro":
            report, daily_tool_results, event_steps, event_warnings = (
                _analyze_market_event(
                    event,
                    watchlist_result.output,
                    universe_result.output,
                    registry,
                    initial_results=daily_tool_results,
                    attempted_tools=daily_attempted_tools,
                    step_suffix=f":{index}",
                    llm_client=llm_client,
                    scope_id=event_id,
                )
            )
            steps.extend(event_steps)
            warnings = tuple(event_warnings)
            if report is None:
                fallback = "deterministic"
                report = _build_rule_report(
                    event,
                    watchlist_result.output,
                    universe_result.output,
                    event_assessments,
                )
                warnings = (*warnings, "深度分析失败，已使用确定性简报。")
        else:
            report = _build_rule_report(
                event,
                watchlist_result.output,
                universe_result.output,
                event_assessments,
            )
        report = _apply_event_brief(report, brief)
        if any(claim.extraction_method == "fallback" for claim in event_claims):
            warnings = (
                *warnings,
                "部分新闻事实由规则降级提取，置信度上限为 35，请核验原始来源。",
            )
        reports.append(report)
        routed_analyses.append(
            RoutedEventAnalysis(
                event=event,
                route=route,
                assessments=event_assessments,
                ledgers=event_ledgers,
                brief=brief,
                report=report,
                fallback=fallback,
                warnings=warnings,
            )
        )

    if not routed_analyses:
        return AgentRun("daily_radar", steps, str(output_path))

    try:
        markdown = render_daily_event_radar(
            rank_result.output,
            window_start,
            window_end,
            tuple(reports),
            routed_analyses,
        )
    except Exception as exc:
        render_result = ToolResult("render_daily_event_radar", "error", "", str(exc))
    else:
        render_result = ToolResult(
            "render_daily_event_radar",
            "success",
            _append_llm_usage(markdown, llm_client),
        )
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
            all_events=all_ranked_events,
            generated_at=window_end,
            routed_analyses=routed_analyses,
        )
    except Exception as exc:
        snapshot_result = ToolResult("write_daily_radar_snapshot", "error", "", str(exc))
        steps.append(_step("write_snapshot", snapshot_result))
        return AgentRun("daily_radar", steps, str(output_path))

    catalog_path = event_catalog_path(json_output_path, snapshot["run"]["id"])
    try:
        write_event_catalog(all_ranked_events, snapshot["run"]["id"], catalog_path)
    except Exception as exc:
        catalog_result = ToolResult("write_event_catalog", "error", "", str(exc))
    else:
        catalog_result = ToolResult("write_event_catalog", "success", str(catalog_path))
    steps.append(_step("write_event_catalog", catalog_result))
    if catalog_result.status == "error":
        return AgentRun("daily_radar", steps, str(output_path))

    try:
        pit_payload = build_point_in_time_payload(
            run_id=snapshot["run"]["id"],
            generated_at=snapshot["run"]["generated_at"],
            events=rank_result.output,
            claims=claim_result.claims,
            routed_analyses=routed_analyses,
            snapshot=snapshot,
        )
        pit_path = write_point_in_time(
            pit_payload,
            point_in_time_path(
                json_output_path,
                snapshot["run"]["id"],
                snapshot["summary"]["scoring_version"],
            ),
        )
    except Exception as exc:
        pit_result = ToolResult("write_point_in_time", "error", "", str(exc))
    else:
        pit_result = ToolResult("write_point_in_time", "success", str(pit_path))
    steps.append(_step("write_point_in_time", pit_result))
    if pit_result.status == "error":
        return AgentRun("daily_radar", steps, str(output_path))

    try:
        for index, (event, report) in enumerate(
            zip(rank_result.output, reports), start=1
        ):
            if report is None:
                continue
            event_id = snapshot["events"][index - 1]["id"]
            event_steps = tuple(
                step for step in steps if step.step_name.endswith(f":{index}")
            )
            write_successful_event_analysis(
                event,
                report,
                event_steps,
                snapshot["events"][index - 1]["warnings"],
                assessments=routed_analyses[index - 1].assessments,
                run_id=snapshot["run"]["id"],
                event_id=event_id,
                rank=index,
                output_path=event_analysis_path(
                    json_output_path, snapshot["run"]["id"], event_id
                ),
            )
    except Exception as exc:
        analyses_result = ToolResult("write_event_analyses", "error", "", str(exc))
    else:
        analyses_result = ToolResult(
            "write_event_analyses",
            "success",
            f"{sum(report is not None for report in reports)} item(s)",
        )
    steps.append(_step("write_event_analyses", analyses_result))
    if analyses_result.status == "error":
        return AgentRun("daily_radar", steps, str(output_path))

    try:
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


def _group_ledgers_by_event(
    ledgers: tuple[EvidenceLedger, ...],
) -> dict[str, tuple[EvidenceLedger, ...]]:
    grouped: dict[str, list[EvidenceLedger]] = {}
    for ledger in ledgers:
        grouped.setdefault(ledger.event_id, []).append(ledger)
    return {event_id: tuple(values) for event_id, values in grouped.items()}


def _group_assessments_by_event(
    assessments: tuple[ImpactAssessment, ...],
) -> dict[str, tuple[ImpactAssessment, ...]]:
    grouped: dict[str, list[ImpactAssessment]] = {}
    for assessment in assessments:
        grouped.setdefault(assessment.event_id, []).append(assessment)
    return {event_id: tuple(values) for event_id, values in grouped.items()}


def _group_claims_by_event(
    claims: tuple[Claim, ...],
) -> dict[str, tuple[Claim, ...]]:
    grouped: dict[str, list[Claim]] = {}
    for claim in claims:
        grouped.setdefault(claim.event_id, []).append(claim)
    return {event_id: tuple(values) for event_id, values in grouped.items()}


def _event_route(
    router: AnalysisRouter,
    event_id: str,
    assessments: tuple[ImpactAssessment, ...],
) -> AnalysisRoute:
    if not assessments:
        return AnalysisRoute(
            event_id=event_id,
            analysis_tier="deterministic",
            priority_level="low",
            reason_codes=("route:deterministic", "route:no_stock_assessment"),
            verify_first=False,
        )
    tier_order = {"pro": 0, "flash": 1, "deterministic": 2, "not_applicable": 3}
    routes = tuple(router.route(assessment) for assessment in assessments)
    strongest = min(routes, key=lambda route: tier_order[route.analysis_tier])
    return replace(
        strongest,
        reason_codes=tuple(
            dict.fromkeys(reason for route in routes for reason in route.reason_codes)
        ),
        verify_first=any(route.verify_first for route in routes),
    )


def _build_rule_report(
    event: MarketEvent,
    watchlist: list[WatchlistItem],
    universe: list[AShareCompany],
    assessments: tuple[ImpactAssessment, ...],
) -> ResearchReport:
    companies = {company.symbol: company for company in universe}
    impacts = []
    for assessment in assessments:
        company = companies.get(assessment.symbol)
        if company is None:
            continue
        magnitude = max(
            assessment.positive_magnitude,
            assessment.negative_magnitude,
        )
        strength = "high" if magnitude >= 60 else "medium" if magnitude >= 35 else "low"
        confidence = (
            "high"
            if assessment.confidence >= 70
            else "medium"
            if assessment.confidence >= 45
            else "low"
        )
        evidence = tuple(
            dict.fromkeys(
                feature_ref
                for feature in (
                    assessment.positive_features,
                    assessment.negative_features,
                )
                if feature is not None
                for score in (
                    feature.directness,
                    feature.exposure,
                    feature.economic_scale,
                    feature.duration,
                    feature.sensitivity,
                )
                for feature_ref in score.evidence_refs
            )
        )
        impacts.append(
            StockImpact(
                symbol=company.symbol,
                name=company.name,
                market=company.market,
                impact_type="direct",
                impact_strength=strength,
                themes=company.themes,
                reasoning="；".join(assessment.reason_codes),
                evidence=evidence,
                risks=(
                    ("正负证据并存，需进一步核验",)
                    if assessment.direction == "mixed"
                    else ()
                ),
                verification_status="verified",
                verification_source=(
                    "local A-share universe and deterministic evidence ledger"
                ),
                watchlist_hit=any(item.symbol == company.symbol for item in watchlist),
                impact_direction=assessment.direction,
                confidence=confidence,
            )
        )
    return ResearchReport(
        raw_news=_market_event_news(event),
        event=EventAnalysis(
            event_type="待判断",
            confidence="low",
            reasoning="基于 Claim、EvidenceLedger 和固定评分规则生成的简报。",
        ),
        value_chain=ValueChainTrace("", ""),
        stock_impacts=tuple(impacts),
        validation_tasks=(),
        stage="待判断",
        action_state="待判断",
    )


def _apply_event_brief(
    report: ResearchReport,
    brief: EventBrief,
) -> ResearchReport:
    return replace(
        report,
        event=replace(
            report.event,
            event_type=brief.event_type,
            themes=brief.themes,
            key_facts=brief.key_facts,
            reasoning=brief.reasoning,
        ),
        value_chain=brief.value_chain,
        validation_tasks=brief.validation_tasks,
    )


def run_market_event_analysis(
    event: MarketEvent,
    *,
    watchlist_path: str | Path = "data/watchlist.example.csv",
    a_share_universe_path: str | Path = "data/a_share_universe.csv",
    evidence_cache_path: str | Path = "data/akshare_cache",
    market_cache_path: str | Path = "data/baostock_cache",
    llm_client: ChatCompletionsClient | None = None,
) -> MarketEventAnalysisOutcome:
    """Run the daily-radar research pipeline for one persisted market event."""

    watchlist_result = read_watchlist_tool(watchlist_path)
    universe_result = read_a_share_universe_tool(a_share_universe_path)
    if watchlist_result.status == "error":
        raise RuntimeError(watchlist_result.error)
    if universe_result.status == "error":
        raise RuntimeError(universe_result.error)
    company_provider = AkShareEvidenceProvider(evidence_cache_path)
    market_provider = FallbackMarketProvider(
        BaoStockMarketProvider(market_cache_path),
        company_provider,
    )
    report, _, steps, warnings = _analyze_market_event(
        event,
        watchlist_result.output,
        universe_result.output,
        _research_tool_registry(company_provider, market_provider),
        llm_client=llm_client,
        scope_id=market_event_id(event),
    )
    if report is None:
        message = steps[-1].summary if steps else "market event analysis failed"
        raise RuntimeError(message)
    try:
        claim_result = ClaimPipeline(
            llm_client,
            Path(evidence_cache_path) / "claims",
        ).extract((event,))
        ledgers = build_evidence_ledgers(
            (event,),
            claim_result.claims,
            universe_result.output,
            watchlist_symbols=(item.symbol for item in watchlist_result.output),
        )
        assessments = build_impact_assessments(
            (event,),
            ledgers,
            universe_result.output,
        )
    except Exception as exc:
        assessments = ()
        warnings.append(f"impact horizon unavailable: {exc}")
        score_result = ToolResult("score_event_impact", "error", (), str(exc))
    else:
        score_result = ToolResult(
            "score_event_impact",
            "success",
            assessments,
            "；".join(claim_result.warnings),
        )
    steps.append(_step("score_event_impact", score_result))
    return MarketEventAnalysisOutcome(
        report,
        tuple(steps),
        tuple(warnings),
        assessments,
    )


def _analyze_market_event(
    event: MarketEvent,
    watchlist: list[WatchlistItem],
    universe: list[AShareCompany],
    registry: ToolRegistry,
    *,
    initial_results: tuple[ToolResult, ...] = (),
    attempted_tools: dict[str, frozenset[str]] | None = None,
    step_suffix: str = "",
    llm_client: ChatCompletionsClient | None = None,
    scope_id: str = "",
) -> tuple[
    ResearchReport | None,
    tuple[ToolResult, ...],
    list[AgentStep],
    list[str],
]:
    steps: list[AgentStep] = []
    attempts = attempted_tools if attempted_tools is not None else {}
    trace_result = trace_news_tool(
        _market_event_news(event),
        watchlist,
        universe,
        **(
            {"client": llm_client, "scope_id": scope_id}
            if llm_client is not None
            else {}
        ),
    )
    steps.append(_step(f"analyze_event{step_suffix}", trace_result))
    if trace_result.status == "error":
        return None, initial_results, steps, [trace_result.error]

    candidate_symbols = tuple(
        dict.fromkeys(
            impact.symbol
            for impact in trace_result.output.stock_impacts
            if (
                impact.market == "A股"
                and impact.verification_status == "verified"
                and impact.impact_type in {"direct", "indirect", "negative"}
                and impact.impact_strength in {"medium", "high"}
            )
        )
    )[:MAX_DAILY_CANDIDATES_PER_EVENT]
    tool_results, evidence_warnings = _complete_candidate_evidence(
        registry,
        candidate_symbols,
        initial_results,
        attempts,
        steps,
    )
    announcements, financials, markets = _evidence_outputs(tool_results)
    report = _apply_tool_verification(
        trace_result.output,
        announcements,
        financials,
        markets,
    )
    identity_warnings = [
        evidence
        for impact in trace_result.output.stock_impacts
        for evidence in impact.evidence
        if "纠正证券代码" in evidence
    ]
    warnings = [
        warning
        for warning in (trace_result.error, *identity_warnings, *evidence_warnings)
        if warning
    ]
    verify_result = ToolResult(
        "verify_event_candidates",
        "success",
        report,
        "；".join(warnings),
    )
    steps.append(_step(f"verify_event_candidates{step_suffix}", verify_result))
    return report, tool_results, steps, warnings


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
    *,
    llm_client: ChatCompletionsClient | None = None,
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

    tasks = plan_research_tasks(
        fetch_result.output,
        watchlist_result.output,
        client=llm_client,
    )
    plan_result = ToolResult("plan_research_tasks", "success", tasks)
    steps.append(_step("plan_research_tasks", plan_result))

    trace_arguments = {
        "news": fetch_result.output,
        "watchlist": watchlist_result.output,
        "a_share_universe": universe_result.output,
    }
    if llm_client is not None:
        trace_arguments["client"] = llm_client
    trace_result = registry.execute("trace_news", trace_arguments)
    steps.append(_step("trace_news", trace_result))
    if trace_result.status == "error":
        return AgentRun("research_agent", steps, str(output_path))

    candidate_symbols = tuple(
        dict.fromkeys(
            impact.symbol
            for impact in trace_result.output.stock_impacts
            if impact.market == "A股" and impact.verification_status == "verified"
        )
    )
    tool_results: tuple[ToolResult, ...] = ()
    try:
        if trace_result.error:
            raise RuntimeError(trace_result.error)
        outcome = run_evidence_tool_calls(
            llm_client or ChatCompletionsClient(),
            registry,
            fetch_result.output,
            trace_result.output,
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
                client=llm_client,
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
    markdown = _append_llm_usage(
        render_research_agent_report(result, steps),
        llm_client,
    )
    render_result = ToolResult("render_research_agent_report", "success", markdown)
    steps.append(_step("render_agent_report", render_result))

    write_result = write_report_tool(render_result.output, output_path)
    steps.append(_step("write_report", write_result))

    return AgentRun("research_agent", steps, str(output_path))


def _append_llm_usage(
    markdown: str,
    client: ChatCompletionsClient | None,
) -> str:
    if client is None or client.usage_session is None:
        return markdown
    return f"{markdown.rstrip()}\n\n{render_usage_markdown(client.usage_session.summary())}\n"


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
