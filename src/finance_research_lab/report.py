from __future__ import annotations

from datetime import date

from .models import NewsTrace, WatchlistItem


def _format_items(items: list[WatchlistItem]) -> str:
    if not items:
        return "- 暂无明确映射，需要人工补充"
    return "\n".join(
        f"- {item.name}（{item.symbol}，{item.market}）：{'; '.join(item.themes)}"
        for item in items
    )


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
