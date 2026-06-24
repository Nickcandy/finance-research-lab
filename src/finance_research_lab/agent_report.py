from __future__ import annotations

from datetime import date

from .agent_models import AgentStep
from .models import Evidence, ResearchAgentResult, ResearchTask
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
