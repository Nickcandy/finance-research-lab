from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from .llm.chat_completions_client import ChatCompletionsClient, UrlOpen
from .models import RawNews, ResearchReport, WatchlistItem
from .research_report_schema import parse_research_report, research_report_json_schema


def analyze_research_report_with_agent(
    news: RawNews,
    watchlist: list[WatchlistItem],
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    urlopen: UrlOpen | None = None,
    env_path: str | Path = ".env",
) -> ResearchReport:
    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
        "env_path": env_path,
    }
    if urlopen is not None:
        client_kwargs["urlopen"] = urlopen

    client = ChatCompletionsClient(**client_kwargs)
    response = client.structured_completion(
        messages=_build_messages(news, watchlist),
        schema_name="research_report",
        schema=research_report_json_schema(),
    )
    try:
        data = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid ResearchReport JSON: {exc}") from exc
    report = parse_research_report(data)
    return replace(report, raw_news=news)


def _build_messages(
    news: RawNews,
    watchlist: list[WatchlistItem],
) -> list[dict[str, str]]:
    system = (
        "你是投资研究结构化分析器。只输出符合 JSON Schema 的对象，不输出 Markdown、解释或代码块。"
        "可以提出可能相关的 A 股候选，但必须谨慎标注证据和不确定性。"
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
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
