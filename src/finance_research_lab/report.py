from __future__ import annotations

from datetime import date

from .models import ResearchReport, NewsTrace, StockImpact, ValidationTask, WatchlistItem


def _format_items(items: list[WatchlistItem]) -> str:
    if not items:
        return "- 暂无明确映射，需要人工补充"
    return "\n".join(
        f"- {item.name}（{item.symbol}，{item.market}）：{'; '.join(item.themes)}"
        for item in items
    )


def _format_stock_impacts(impacts: tuple[StockImpact, ...]) -> str:
    if not impacts:
        return "- 暂无明确映射，需要人工补充"

    lines: list[str] = []
    for impact in impacts:
        themes = " / ".join(impact.themes) if impact.themes else "未标注主题"
        evidence = "；".join(impact.evidence) if impact.evidence else "待补充"
        risks = "；".join(impact.risks) if impact.risks else "待补充"
        lines.extend(
            [
                f"- {impact.name}（{impact.symbol}，{impact.market}）："
                f"{impact.impact_type} / {impact.impact_strength}",
                f"  - 校验：{_verification_label(impact)}",
                f"  - Watchlist：{'命中' if impact.watchlist_hit else '未命中'}",
                f"  - 主题：{themes}",
                f"  - 理由：{impact.reasoning or '待补充'}",
                f"  - 证据：{evidence}",
                f"  - 风险：{risks}",
            ]
        )
    return "\n".join(lines)


def _verification_label(impact: StockImpact) -> str:
    labels = {
        "verified": "已校验",
        "unverified": "待确认",
        "excluded": "已排除",
    }
    label = labels.get(impact.verification_status, impact.verification_status)
    if impact.verification_source:
        return f"{label}（{impact.verification_source}）"
    return label


def _filter_impacts(impacts: tuple[StockImpact, ...], status: str) -> tuple[StockImpact, ...]:
    return tuple(impact for impact in impacts if impact.verification_status == status)


def _watchlist_hits(impacts: tuple[StockImpact, ...]) -> tuple[StockImpact, ...]:
    return tuple(impact for impact in impacts if impact.watchlist_hit)


def _format_validation_tasks(tasks: tuple[ValidationTask, ...]) -> str:
    if not tasks:
        return "- [ ] 暂无验证任务"
    return "\n".join(f"- [ ] {task.question}（需要：{task.data_needed}）" for task in tasks)


def render_research_report(report: ResearchReport, report_date: date | None = None) -> str:
    report_date = report_date or date.today()
    chain = " -> ".join(report.value_chain.chain_steps)
    themes = " / ".join(report.event.themes) if report.event.themes else "待判断"
    key_facts = "\n".join(f"- {fact}" for fact in report.event.key_facts) or "- 待补充"

    return f"""# 研究报告：{report.raw_news.headline}

> 生成日期：{report_date.isoformat()}
> 来源：{report.raw_news.source}
> 用途：研究辅助，不构成投资建议。

## 1. 原始事件

- 标题：{report.raw_news.headline}
- 来源：{report.raw_news.source}
- URL：{report.raw_news.url or '未提供'}
- 发布时间：{report.raw_news.published_at or '未提供'}

## 2. 事件理解

- 事件类型：{report.event.event_type}
- 主题：{themes}
- 来源质量：{report.event.source_quality}
- 置信度：{report.event.confidence}
- 推理方式：{report.event.reasoning}

### 关键事实

{key_facts}

## 3. 产业链路径

- 谁付钱：{report.value_chain.payer}
- 谁收钱：{report.value_chain.receiver}
- 影响方向：{report.value_chain.impact_direction}
- 产业链路径：`{chain}`
- 推理方式：{report.value_chain.reasoning}

## 4. 已校验 A 股候选

{_format_stock_impacts(_filter_impacts(report.stock_impacts, "verified"))}

## 5. 待确认候选

{_format_stock_impacts(_filter_impacts(report.stock_impacts, "unverified"))}

## 6. 风险排除 / 伪相关

{_format_stock_impacts(_filter_impacts(report.stock_impacts, "excluded"))}

## 7. Watchlist 命中

{_format_stock_impacts(_watchlist_hits(report.stock_impacts))}

## 8. 当前阶段

- 阶段：{report.stage}
- 动作状态：{report.action_state}

## 9. 后续验证点

{_format_validation_tasks(report.validation_tasks)}

## 10. 备注

这份报告只做事件追源和候选校验整理。当前结果可能来自规则 fallback，后续需要由 Agent、工具和人工复核共同验证。
"""


def render_news_trace(trace: NewsTrace, report_date: date | None = None) -> str:
    report_date = report_date or date.today()
    chain = " -> ".join(trace.value_chain)
    checks = "\n".join(f"- [ ] {point}" for point in trace.verification_points)

    return f"""# 热点追源：{trace.headline}

> 生成日期：{report_date.isoformat()}  
> 来源：{trace.source}  
> 用途：研究辅助，不构成投资建议。

## 1. 原始新闻

- 标题：{trace.headline}
- 来源：{trace.source}
- 新闻类型：{trace.news_type}
- 可信等级：待复核

## 2. 产业链拆解

- 谁付钱：{trace.payer}
- 谁收钱：{trace.receiver}
- 产业链路径：`{chain}`

## 3. 市场映射

### 直接受益

{_format_items(trace.direct_beneficiaries)}

### 间接受益

{_format_items(trace.indirect_beneficiaries)}

### 情绪映射

{_format_items(trace.sentiment_mappings)}

## 4. 当前阶段

- 阶段：{trace.stage}
- 动作状态：{trace.action_state}

## 5. 后续验证点

{checks}

## 6. 备注

这份报告只做热点追源和观察池整理。若主题已经连续大涨，优先标记为“等回调 / 高潮勿追”，不要把新闻热度直接当成买点。
"""
