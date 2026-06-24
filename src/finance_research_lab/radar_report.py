from __future__ import annotations

from datetime import date

from .models import ResearchReport, StockImpact, ValidationTask


def render_opportunity_radar(
    reports: list[ResearchReport],
    report_date: date | None = None,
) -> str:
    report_date = report_date or date.today()

    return f"""# 今日投资机会雷达 {report_date.isoformat()}

> 分析新闻数：{len(reports)}
> 用途：研究辅助，不构成投资建议。

## 1. 今日核心结论
{_core_findings(reports)}

## 2. 热点事件追源
{_event_traces(reports)}

## 3. 中长线观察
{_format_candidates(_long_term_candidates(reports))}

## 4. 短期交易机会
{_format_candidates(_short_term_candidates(reports))}

## 5. 高位不追 / 风险排除
{_format_candidates(_risk_candidates(reports))}

## 6. 明天验证点
{_format_validation_tasks(_dedupe_validation_tasks(reports))}

## 7. 待复盘记录
暂无
"""


def _core_findings(reports: list[ResearchReport]) -> str:
    if not reports:
        return "暂无"

    lines: list[str] = []
    for report in reports[:5]:
        themes = " / ".join(report.event.themes) if report.event.themes else "待判断"
        lines.append(
            f"- {report.raw_news.headline}：{report.event.event_type}，主题 {themes}，"
            f"阶段 {report.stage}，动作 {report.action_state}"
        )
    return "\n".join(lines[:5])


def _event_traces(reports: list[ResearchReport]) -> str:
    if not reports:
        return "暂无"

    sections: list[str] = []
    for index, report in enumerate(reports, start=1):
        themes = " / ".join(report.event.themes) if report.event.themes else "待判断"
        chain = " -> ".join(report.value_chain.chain_steps) or "待判断"
        impacts = _format_impacts(report.stock_impacts)
        sections.append(
            f"""### 2.{index} {report.raw_news.headline}
- 来源：{report.raw_news.source}
- URL：{report.raw_news.url or '未提供'}
- 事件类型：{report.event.event_type}
- 主题：{themes}
- 产业链路径：{report.value_chain.payer} -> {report.value_chain.receiver} -> {chain}
- 涉及标的及影响：
{impacts}"""
        )
    return "\n\n".join(sections)


def _long_term_candidates(reports: list[ResearchReport]) -> list[tuple[ResearchReport, StockImpact]]:
    return [
        (report, impact)
        for report in reports
        for impact in report.stock_impacts
        if impact.impact_type == "direct" and impact.impact_strength in {"high", "medium"}
    ]


def _short_term_candidates(reports: list[ResearchReport]) -> list[tuple[ResearchReport, StockImpact]]:
    return [
        (report, impact)
        for report in reports
        for impact in report.stock_impacts
        if report.stage in {"启动", "验证"} and report.action_state in {"可小仓试", "等回调"}
    ]


def _risk_candidates(reports: list[ResearchReport]) -> list[tuple[ResearchReport, StockImpact]]:
    return [
        (report, impact)
        for report in reports
        for impact in report.stock_impacts
        if report.stage in {"高潮", "分歧"}
        or impact.impact_strength == "low"
        or report.action_state == "高潮勿追"
    ]


def _format_candidates(candidates: list[tuple[ResearchReport, StockImpact]]) -> str:
    if not candidates:
        return "暂无"
    return "\n".join(_candidate_line(report, impact) for report, impact in candidates)


def _candidate_line(report: ResearchReport, impact: StockImpact) -> str:
    return (
        f"- {impact.name}（{impact.symbol}，{impact.market}）："
        f"{impact.impact_type} / {impact.impact_strength}；"
        f"阶段 {report.stage}；动作 {report.action_state}；"
        f"来源：{report.raw_news.headline}；理由：{impact.reasoning or '待补充'}"
    )


def _format_impacts(impacts: tuple[StockImpact, ...]) -> str:
    if not impacts:
        return "  - 暂无"
    return "\n".join(f"  {_candidate_line_for_trace(impact)}" for impact in impacts)


def _candidate_line_for_trace(impact: StockImpact) -> str:
    return (
        f"- {impact.name}（{impact.symbol}，{impact.market}）："
        f"{impact.impact_type} / {impact.impact_strength}；{impact.reasoning or '待补充'}"
    )


def _dedupe_validation_tasks(reports: list[ResearchReport]) -> list[ValidationTask]:
    tasks: list[ValidationTask] = []
    seen: set[str] = set()
    for report in reports:
        for task in report.validation_tasks:
            if task.question in seen:
                continue
            seen.add(task.question)
            tasks.append(task)
    return tasks


def _format_validation_tasks(tasks: list[ValidationTask]) -> str:
    if not tasks:
        return "暂无"
    return "\n".join(f"- [ ] {task.question}（需要：{task.data_needed}）" for task in tasks)
