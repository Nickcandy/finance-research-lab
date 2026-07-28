from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from .llm.chat_completions_client import ChatCompletionsClient, UrlOpen
from .models import NewsItem, ResearchReport, WatchlistItem
from .research_report_schema import parse_research_report, research_report_json_schema


def analyze_research_report_with_agent(
    news: NewsItem,
    watchlist: list[WatchlistItem],
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    urlopen: UrlOpen | None = None,
    env_path: str | Path = ".env",
    evidence_context: list[dict[str, Any]] | None = None,
    client: ChatCompletionsClient | None = None,
    scope_id: str = "",
) -> ResearchReport:
    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
        "env_path": env_path,
    }
    if urlopen is not None:
        client_kwargs["urlopen"] = urlopen

    llm_client = client or ChatCompletionsClient(**client_kwargs)
    response = llm_client.structured_completion(
        messages=_build_messages(news, watchlist, evidence_context),
        schema_name="research_report",
        schema=research_report_json_schema(),
        scope_id=scope_id,
    )
    try:
        data = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid ResearchReport JSON: {exc}") from exc
    report = parse_research_report(data)
    return replace(report, raw_news=news)


def _build_messages(
    news: NewsItem,
    watchlist: list[WatchlistItem],
    evidence_context: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    system = (
        "你是投资研究结构化分析器。只输出符合 JSON Schema 的对象，不输出 Markdown、解释或代码块。"
        "可以提出可能相关的 A 股候选，但必须谨慎标注证据和不确定性。"
        "股票 impact_type 只描述直接、间接、情绪或伪相关，利好利空必须写入 "
        "impact_direction；confidence 表示该方向判断的证据置信度。"
        "不得把产业链相关性自动解释为利好，也不得预测具体涨跌幅。"
        "产业链分析遵循 Serenity 方法：先写真实需求和系统变化，再按下游需求、系统集成、模块、"
        "芯片器件、工艺封测、设备测试、材料耗材、基础设施拆层；先判断供应商数量、认证周期、"
        "扩产难度和替代难度，再提出公司。没有订单、收入、客户认证或产能证据时，不得声称存在瓶颈。"
        "每个候选必须说明产业链位置、支持证据、反方理由和什么情况应降低判断。"
        "watchlist 只是用户个人上下文，不是候选股票边界；最终候选会由 tools 校验。"
        "不确定的字段填“待判断”、“unknown”或空数组。"
        "输出仅用于研究辅助，不构成投资建议。"
    )
    payload = {
        "news": {
            "headline": news.headline,
            "source": news.source,
            "url": news.url,
            "published_at": news.published_at,
            "body": news.body,
        },
        "watchlist": [
            {
                "symbol": item.symbol,
                "name": item.name,
                "market": item.market,
                "themes": list(item.themes),
                "thesis": item.thesis,
                "risks": item.risks,
            }
            for item in watchlist
        ],
        "evidence": evidence_context or [],
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
