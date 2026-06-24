from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .llm.chat_completions_client import ChatCompletionsClient, UrlOpen
from .models import RawNews, ResearchTask, WatchlistItem
from .research_report_schema import VALIDATION_STATUSES, _object_schema


def research_tasks_json_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "tasks": {
                "type": "array",
                "items": _object_schema(
                    {
                        "question": {"type": "string"},
                        "rationale": {"type": "string"},
                        "data_needed": {"type": "string"},
                        "status": {"type": "string", "enum": sorted(VALIDATION_STATUSES)},
                    }
                ),
            }
        }
    )


def plan_research_tasks(
    news: RawNews,
    watchlist: list[WatchlistItem],
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    urlopen: UrlOpen | None = None,
    env_path: str | Path = ".env",
) -> tuple[ResearchTask, ...]:
    try:
        tasks = analyze_research_tasks_with_agent(
            news,
            watchlist,
            api_key=api_key,
            model=model,
            base_url=base_url,
            urlopen=urlopen,
            env_path=env_path,
        )
    except Exception:
        return fallback_research_tasks(news, watchlist)
    if not tasks:
        return fallback_research_tasks(news, watchlist)
    return tasks


def analyze_research_tasks_with_agent(
    news: RawNews,
    watchlist: list[WatchlistItem],
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    urlopen: UrlOpen | None = None,
    env_path: str | Path = ".env",
) -> tuple[ResearchTask, ...]:
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
        schema_name="research_tasks",
        schema=research_tasks_json_schema(),
    )
    try:
        data = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid ResearchTask JSON: {exc}") from exc
    return parse_research_tasks(data)


def fallback_research_tasks(
    news: RawNews,
    watchlist: list[WatchlistItem],
) -> tuple[ResearchTask, ...]:
    del news, watchlist
    return (
        ResearchTask(
            "是否能找到最早官方来源或可靠媒体原文？",
            "先确认原始事实，避免二手报道或标题党误导。",
            "官方公告、监管文件、公司新闻稿或可靠媒体原文",
        ),
        ResearchTask(
            "事件是否已经对应真实订单、收入、资本开支或监管落地？",
            "研究结论需要落到可验证的业务或政策事实。",
            "公告、财报、订单金额、客户名称、政策原文或执行时间表",
        ),
        ResearchTask(
            "新闻主题与股票池标的的映射是否成立？",
            "区分直接受益、间接受益、情绪映射和伪相关。",
            "股票池主题、公司主营、客户结构、产业链位置和风险点",
        ),
        ResearchTask(
            "当前热度阶段是否适合继续跟踪？",
            "同一事件在启动、验证、高潮和退潮阶段的处理方式不同。",
            "价格位置、成交额变化、板块扩散、公告节奏和市场反馈",
        ),
    )


def parse_research_tasks(data: dict[str, Any]) -> tuple[ResearchTask, ...]:
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("Expected array at tasks")

    parsed: list[ResearchTask] = []
    for index, item in enumerate(tasks):
        if not isinstance(item, dict):
            raise ValueError(f"Expected object at tasks.{index}")
        status = item.get("status")
        if status not in VALIDATION_STATUSES:
            raise ValueError(f"Invalid status at tasks.{index}.status: {status}")
        parsed.append(
            ResearchTask(
                question=_string(item.get("question"), f"tasks.{index}.question"),
                rationale=_string(item.get("rationale"), f"tasks.{index}.rationale"),
                data_needed=_string(item.get("data_needed"), f"tasks.{index}.data_needed"),
                status=status,
            )
        )
    return tuple(parsed)


def _build_messages(
    news: RawNews,
    watchlist: list[WatchlistItem],
) -> list[dict[str, str]]:
    system = (
        "你是投资研究 Agent 的任务规划器。只输出符合 JSON Schema 的对象。"
        "任务只能用于研究验证，不要给买卖建议。"
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


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Expected string at {path}")
    return value
