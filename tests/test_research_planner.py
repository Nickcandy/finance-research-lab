from __future__ import annotations

import json

import pytest

from finance_research_lab.models import RawNews, ResearchTask, WatchlistItem
from finance_research_lab.research_planner import (
    fallback_research_tasks,
    plan_research_tasks,
)


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _llm_payload(content: str | None = None, refusal: str | None = None) -> dict[str, object]:
    message: dict[str, object] = {"role": "assistant"}
    if content is not None:
        message["content"] = content
    if refusal is not None:
        message["refusal"] = refusal
    return {
        "model": "gpt-4o-mini",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        "choices": [{"message": message}],
    }


def test_plan_research_tasks_with_agent_returns_structured_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "tasks": [
            {
                "question": "官方来源是否确认 AI capex 增长？",
                "rationale": "先确认原始事实，避免二手报道误读。",
                "data_needed": "公司公告或可靠媒体原文",
                "status": "pending",
            }
        ]
    }

    def fake_urlopen(request: object, timeout: int) -> FakeHTTPResponse:
        return FakeHTTPResponse(_llm_payload(json.dumps(payload, ensure_ascii=False)))

    tasks = plan_research_tasks(
        _news(),
        [_watchlist_item()],
        api_key="test-key",
        model="gpt-4o-mini",
        urlopen=fake_urlopen,
    )

    assert tasks == (
        ResearchTask(
            question="官方来源是否确认 AI capex 增长？",
            rationale="先确认原始事实，避免二手报道误读。",
            data_needed="公司公告或可靠媒体原文",
        ),
    )


@pytest.mark.parametrize("content", ["{bad-json", '{"tasks": []}'])
def test_plan_research_tasks_falls_back_when_agent_output_is_unusable(content: str) -> None:
    def fake_urlopen(request: object, timeout: int) -> FakeHTTPResponse:
        return FakeHTTPResponse(_llm_payload(content))

    tasks = plan_research_tasks(
        _news(),
        [_watchlist_item()],
        api_key="test-key",
        model="gpt-4o-mini",
        urlopen=fake_urlopen,
    )

    assert tasks == fallback_research_tasks(_news(), [_watchlist_item()])
    assert len(tasks) == 4


def test_plan_research_tasks_falls_back_when_api_key_is_missing(tmp_path) -> None:
    tasks = plan_research_tasks(
        _news(),
        [_watchlist_item()],
        env_path=tmp_path / "missing.env",
    )

    assert len(tasks) == 4
    assert tasks[0].question == "是否能找到最早官方来源或可靠媒体原文？"


def _news() -> RawNews:
    return RawNews(
        headline="AI capex increases",
        source="Example News",
        url="https://news.example.com/ai-capex",
        body="Microsoft increased AI data center spending and optical module demand.",
    )


def _watchlist_item() -> WatchlistItem:
    return WatchlistItem("300308.SZ", "中际旭创", "A股", ("AI", "数据中心", "光模块"))
