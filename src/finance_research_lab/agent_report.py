from __future__ import annotations

from datetime import date

from .agent_models import AgentStep
from .models import (
    CompanyAnnouncement,
    Evidence,
    EvidencePlan,
    FinancialSnapshot,
    MarketSnapshot,
    ResearchAgentResult,
    ResearchTask,
    ValueChainScore,
)
from .report import render_research_report


def render_research_agent_report(
    result: ResearchAgentResult,
    steps: list[AgentStep],
    report_date: date | None = None,
) -> str:
    report_date = report_date or date.today()
    return f"""# AI Research Agent 报告：{result.report.raw_news.headline}

> 生成日期：{report_date.isoformat()}
> 用途：研究辅助，不构成投资建议。

## Agent 执行摘要
{_format_steps(steps)}

## 研究任务
{_format_tasks(result.tasks)}

## Evidence-first 研究计划
{_format_evidence_first(result)}

## 证据列表
{_format_evidence(result.evidence)}

{render_research_report(result.report, report_date)}
"""


def _format_steps(steps: list[AgentStep]) -> str:
    if not steps:
        return "- 暂无"
    return "\n".join(
        f"- {step.step_name} via {step.tool_name}: {step.status}；{step.summary}"
        for step in steps
    )


def _format_tasks(tasks: tuple[ResearchTask, ...]) -> str:
    if not tasks:
        return "- 暂无"
    lines: list[str] = []
    for task in tasks:
        lines.extend(
            [
                f"- [ ] {task.question}",
                f"  - 理由：{task.rationale}",
                f"  - 需要：{task.data_needed}",
                f"  - 状态：{task.status}",
            ]
        )
    return "\n".join(lines)


def _format_evidence_first(result: ResearchAgentResult) -> str:
    sections = [
        "### 事件类型",
        _format_classification(result),
        "### 证据计划",
        _format_evidence_plan(result.evidence_plan),
        "### 支持证据",
        _format_supporting_evidence(
            result.company_announcements,
            result.financial_snapshots,
            result.market_snapshots,
        ),
        "### 反对证据",
        "- 当前为 V1.5 mock provider，反对证据待接入真实公告、财报和行情后补充。",
        "### 上下游 scale",
        _format_value_chain_scores(result.value_chain_scores),
        "### 市场反应",
        _format_market_snapshots(result.market_snapshots),
        "### 下一步验证",
        _format_next_questions(result.evidence_plan),
    ]
    return "\n".join(sections)


def _format_classification(result: ResearchAgentResult) -> str:
    if result.classification is None:
        return "- 待补充"
    classification = result.classification
    candidates = " / ".join(classification.candidate_symbols) or "待补充"
    return (
        f"- 类型：{classification.event_type}\n"
        f"- 候选标的：{candidates}\n"
        f"- 置信度：{classification.confidence}\n"
        f"- 理由：{classification.reasoning or '待补充'}"
    )


def _format_evidence_plan(plan: EvidencePlan | None) -> str:
    if plan is None:
        return "- 待补充"
    tools = " / ".join(plan.required_tools) or "待补充"
    questions = "\n".join(f"- [ ] {question}" for question in plan.questions) or "- [ ] 待补充"
    return f"- 需要工具：{tools}\n{questions}"


def _format_supporting_evidence(
    announcements: tuple[CompanyAnnouncement, ...],
    financials: tuple[FinancialSnapshot, ...],
    snapshots: tuple[MarketSnapshot, ...],
) -> str:
    lines: list[str] = []
    for announcement in announcements:
        lines.append(f"- 公告：{announcement.title}；摘要：{announcement.summary or '待补充'}")
    for financial in financials:
        lines.append(
            f"- 财报：{financial.symbol} {financial.report_period}；"
            f"收入：{_format_optional_number(financial.revenue)}；"
            f"净利润：{_format_optional_number(financial.net_profit)}"
        )
    for snapshot in snapshots:
        lines.append(
            f"- 行情：{snapshot.symbol} 最近 {snapshot.lookback_days} 日；"
            f"涨跌幅：{snapshot.pct_chg}%；成交额：{snapshot.amount:g}"
        )
    if not lines:
        return "- 待补充"
    return "\n".join(lines)


def _format_value_chain_scores(scores: tuple[ValueChainScore, ...]) -> str:
    if not scores:
        return "- 待补充"
    lines: list[str] = []
    for score in scores:
        lines.append(
            f"- {score.symbol}：上游 {score.upstream_relevance_score} / "
            f"下游 {score.downstream_relevance_score} / "
            f"收入弹性 {score.revenue_elasticity_score}；{score.reasoning}"
        )
    return "\n".join(lines)


def _format_market_snapshots(snapshots: tuple[MarketSnapshot, ...]) -> str:
    if not snapshots:
        return "- 待补充"
    return "\n".join(
        f"- {snapshot.symbol}：收盘 {snapshot.close:g}，涨跌幅 {snapshot.pct_chg:g}%，"
        f"成交量 {snapshot.volume:g}，成交额 {snapshot.amount:g}"
        for snapshot in snapshots
    )


def _format_next_questions(plan: EvidencePlan | None) -> str:
    if plan is None or not plan.questions:
        return "- [ ] 待补充"
    return "\n".join(f"- [ ] {question}" for question in plan.questions)


def _format_evidence(evidence: tuple[Evidence, ...]) -> str:
    if not evidence:
        return "- 暂无"
    lines: list[str] = []
    for item in evidence:
        supports = "；".join(item.supports) if item.supports else "待关联"
        lines.extend(
            [
                f"- {item.title}（{item.source_type}）",
                f"  - URL：{item.url or '未提供'}",
                f"  - 摘要：{item.summary}",
                f"  - 支持：{supports}",
            ]
        )
    return "\n".join(lines)


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return "待补充"
    return f"{value:g}"
