from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from .impact_scoring import (
    format_impact_score,
    impact_direction_label,
    stock_impact_score,
    summarize_event_impact,
)
from .models import MarketEvent, ResearchReport, StockImpact
from .impact_assessment import ImpactAssessment

SHANGHAI = ZoneInfo("Asia/Shanghai")
PENDING_SECTION = "暂无（Task 5/6 尚未接入）"


class RoutedAnalysis(Protocol):
    event: MarketEvent
    assessments: tuple[ImpactAssessment, ...]
    brief: Any

    @property
    def route(self) -> Any: ...


def render_daily_event_radar(
    events: tuple[MarketEvent, ...],
    window_start: datetime,
    window_end: datetime,
    reports: tuple[ResearchReport | None, ...] | None = None,
    routed_analyses: Sequence[RoutedAnalysis] = (),
) -> str:
    """Render ranked market events into the stable daily radar skeleton."""

    if not events:
        raise ValueError("events must not be empty")
    window_start = _shanghai_time(window_start)
    window_end = _shanghai_time(window_end)
    if window_start >= window_end:
        raise ValueError("window_start must be earlier than window_end")
    if any(not event.items for event in events):
        raise ValueError("MarketEvent items must not be empty")
    if reports is not None and len(reports) != len(events):
        raise ValueError("reports must align with events")

    verified = (
        _format_candidates(reports, "verified", routed_analyses)
        if reports is not None
        else PENDING_SECTION
    )
    unverified = (
        _format_candidates(reports, "unverified", routed_analyses)
        if reports is not None
        else PENDING_SECTION
    )
    excluded = (
        _format_candidates(reports, "excluded", routed_analyses)
        if reports is not None
        else PENDING_SECTION
    )
    watchlist_hits = (
        _format_candidates(reports, "watchlist", routed_analyses)
        if reports is not None
        else PENDING_SECTION
    )
    validation_tasks = _format_validation_tasks(reports) if reports is not None else PENDING_SECTION
    review = "暂无" if reports is not None else PENDING_SECTION
    major_events, ranked_stocks, verify_first, watchlist_risks = _scored_sections(
        reports,
        routed_analyses,
    )

    return f"""# 今日 A股投资研究雷达 {window_end.date().isoformat()}

> 时间窗口：{window_start.isoformat(timespec="seconds")} 至 {window_end.isoformat(timespec="seconds")}
> 热点事件数：{len(events)}
> 用途：研究辅助，不构成投资建议。

## 1. 今日核心事件

{_event_sections(events, reports, routed_analyses)}

## 2. 已校验 A股候选

{verified}

## 3. 待确认候选

{unverified}

## 4. 风险排除 / 伪相关

{excluded}

## 5. Watchlist 命中

{watchlist_hits}

## 6. 明日验证任务

{validation_tasks}

## 7. 待复盘记录

{review}

## 8. 重大事件榜

{major_events}

## 9. 重点股票榜

{ranked_stocks}

## 10. 高影响待核验

{verify_first}

## 11. Watchlist 风险预警

{watchlist_risks}

> 影响分表示研究优先级，不是收益预测，不构成投资建议。
"""


def _scored_sections(
    reports: tuple[ResearchReport | None, ...] | None,
    routed_analyses: Sequence[RoutedAnalysis],
) -> tuple[str, str, str, str]:
    if not routed_analyses:
        return ("暂无", "暂无", "暂无", "暂无")
    major = sorted(
        routed_analyses,
        key=lambda routed: (
            -max(
                (assessment.event_importance for assessment in routed.assessments),
                default=0,
            ),
            routed.event.title,
        ),
    )
    major_lines = [
        (
            f"- {routed.event.title}：重要度 "
            f"{max((item.event_importance for item in routed.assessments), default=0)}；"
            f"{routed.route.priority_level} / {routed.route.analysis_tier}"
        )
        for routed in major
    ]
    names, watchlist = _report_company_context(reports)
    by_symbol: dict[str, list[ImpactAssessment]] = {}
    for routed in routed_analyses:
        for assessment in routed.assessments:
            if assessment.symbol:
                by_symbol.setdefault(assessment.symbol, []).append(assessment)
    stock_rows = sorted(
        by_symbol.items(),
        key=lambda item: (
            -max(max(value.positive_magnitude, value.negative_magnitude) for value in item[1]),
            item[0],
        ),
    )
    stock_lines = [
        (
            f"- {names.get(symbol, symbol)}（{symbol}）：正向 "
            f"{max(item.positive_magnitude for item in assessments)} / 负向 "
            f"{max(item.negative_magnitude for item in assessments)} / 置信度 "
            f"{max(item.confidence for item in assessments)}"
        )
        for symbol, assessments in stock_rows
    ]
    verify_lines = [
        f"- {routed.event.title}：高影响低置信，优先补充原始证据。"
        for routed in routed_analyses
        if routed.route.verify_first
    ]
    risk_lines = [
        (
            f"- {names.get(symbol, symbol)}（{symbol}）：负向影响 "
            f"{max(item.negative_magnitude for item in assessments)}"
        )
        for symbol, assessments in stock_rows
        if symbol in watchlist and max(item.negative_magnitude for item in assessments) >= 60
    ]
    return (
        "\n".join(major_lines) or "暂无",
        "\n".join(stock_lines) or "暂无",
        "\n".join(verify_lines) or "暂无",
        "\n".join(risk_lines) or "暂无",
    )


def _report_company_context(
    reports: tuple[ResearchReport | None, ...] | None,
) -> tuple[dict[str, str], set[str]]:
    names: dict[str, str] = {}
    watchlist: set[str] = set()
    for report in reports or ():
        if report is None:
            continue
        for impact in report.stock_impacts:
            names.setdefault(impact.symbol, impact.name)
            if impact.watchlist_hit:
                watchlist.add(impact.symbol)
    return names, watchlist


def _event_sections(
    events: tuple[MarketEvent, ...],
    reports: tuple[ResearchReport | None, ...] | None,
    routed_analyses: Sequence[RoutedAnalysis],
) -> str:
    routed_by_title = {routed.event.title: routed for routed in routed_analyses}
    sections: list[str] = []
    for index, event in enumerate(events, start=1):
        sources = tuple(
            dict.fromkeys(item.source.strip() or item.source_type for item in event.items)
        )
        urls = event.source_urls
        url_lines = "\n".join(f"  - {url}" for url in urls) if urls else "  - 暂无可用 URL"
        report = reports[index - 1] if reports is not None else None
        research = _event_research(
            report,
            reports is not None,
            routed_by_title.get(event.title),
        )
        sections.append(
            f"""### 1.{index} {event.title}
- 最新时间：{event.items[0].published_at or "未提供"}
- 报道数量：{len(event.items)}
- 独立来源：{len(sources)}（{" / ".join(sources)}）
- 事件类型：{research[0]}
- 主题：{research[1]}
- 产业链：{research[2]}
- 总体影响：{research[3]}
- 来源 URL：
{url_lines}"""
        )
    return "\n\n".join(sections)


def _event_research(
    report: ResearchReport | None,
    research_attempted: bool,
    routed: RoutedAnalysis | None = None,
) -> tuple[str, str, str, str]:
    if report is None:
        value = "分析失败，详见 AgentStep" if research_attempted else "待研究"
        return value, value, value, value
    brief = getattr(routed, "brief", None) if routed is not None else None
    event_type = brief.event_type if brief is not None else report.event.event_type
    themes = " / ".join(brief.themes if brief is not None else report.event.themes) or "待判断"
    value_chain = brief.value_chain if brief is not None else report.value_chain
    chain = " -> ".join(value_chain.chain_steps) or "未识别到可验证价值链"
    if routed is not None and routed.assessments:
        directions = {assessment.direction for assessment in routed.assessments}
        direction = next(iter(directions)) if len(directions) == 1 else "mixed"
        positive = max(item.positive_magnitude for item in routed.assessments)
        negative = max(item.negative_magnitude for item in routed.assessments)
        confidence = max(item.confidence for item in routed.assessments)
        summary = (
            f"{impact_direction_label(direction)} / 正向 {positive} / "
            f"负向 {negative} / 置信度 {confidence}"
        )
        return event_type, themes, chain, summary
    impact = summarize_event_impact(report)
    summary = (
        f"{impact_direction_label(impact.direction)} / "
        f"{format_impact_score(impact.score)} / 置信度 {impact.confidence}"
    )
    return event_type, themes, chain, summary


def _format_candidates(
    reports: tuple[ResearchReport | None, ...],
    category: str,
    routed_analyses: Sequence[RoutedAnalysis] = (),
) -> str:
    grouped: dict[str, list[tuple[ResearchReport, StockImpact]]] = {}
    for report in reports:
        if report is None:
            continue
        for impact in report.stock_impacts:
            if impact.market != "A股":
                continue
            if category == "watchlist":
                matched = impact.watchlist_hit
            elif category == "excluded":
                matched = (
                    impact.verification_status == "excluded"
                    or impact.impact_type == "false_positive"
                )
            elif category == "unverified":
                matched = (
                    impact.verification_status == "unverified"
                    and impact.impact_type != "false_positive"
                )
            else:
                matched = (
                    impact.verification_status == category
                    and impact.impact_type != "false_positive"
                )
            if matched:
                grouped.setdefault(impact.symbol, []).append((report, impact))
    if not grouped:
        return "暂无"
    assessments_by_symbol: dict[str, list[ImpactAssessment]] = {}
    for routed in routed_analyses:
        for assessment in routed.assessments:
            assessments_by_symbol.setdefault(assessment.symbol, []).append(assessment)
    return "\n".join(
        _candidate_line(
            items,
            category,
            assessments_by_symbol.get(items[0][1].symbol, ()),
        )
        for items in grouped.values()
    )


def _candidate_line(
    items: list[tuple[ResearchReport, StockImpact]],
    category: str,
    assessments: Sequence[ImpactAssessment] = (),
) -> str:
    first = items[0][1]
    event_titles = _unique(report.raw_news.headline for report, _ in items)
    if assessments:
        impact_types = [
            f"正向 {max(item.positive_magnitude for item in assessments)} / "
            f"负向 {max(item.negative_magnitude for item in assessments)} / "
            f"置信度 {max(item.confidence for item in assessments)}"
        ]
    else:
        impact_types = _unique(
            f"{impact_direction_label(impact.impact_direction)} "
            f"{format_impact_score(stock_impact_score(impact))}（{impact.confidence}） / "
            f"{impact.impact_type} / {impact.impact_strength}"
            for _, impact in items
        )
    reasons = _unique(impact.reasoning for _, impact in items if impact.reasoning)
    evidence = _unique(value for _, impact in items for value in impact.evidence if value)
    risks = _unique(value for _, impact in items for value in impact.risks if value)
    verification_sources = _unique(
        impact.verification_source for _, impact in items if impact.verification_source
    )
    if category == "excluded":
        verification = "已排除"
    elif first.verification_status == "verified":
        verification = " / ".join(verification_sources) or "已校验"
    else:
        verification = "证据不足，待补公告、财报或行情"
    return (
        f"- {first.name}（{first.symbol}，{first.market}）：{'；'.join(impact_types)}；"
        f"校验：{verification}；Watchlist {'命中' if any(i.watchlist_hit for _, i in items) else '未命中'}；"
        f"来源事件：{' / '.join(event_titles)}；理由：{'；'.join(reasons) or '待补充'}；"
        f"证据：{'；'.join(evidence) or '待补充'}；风险：{'；'.join(risks) or '待补充'}"
    )


def _format_validation_tasks(reports: tuple[ResearchReport | None, ...]) -> str:
    tasks = _unique(
        f"{task.question}（需要：{task.data_needed}）"
        for report in reports
        if report is not None
        for task in report.validation_tasks
    )
    if not tasks:
        return "暂无"
    return "\n".join(f"- [ ] {task}" for task in tasks)


def _unique(values) -> list[str]:
    return list(dict.fromkeys(values))


def _shanghai_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI)
    return value.astimezone(SHANGHAI)
