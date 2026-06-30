from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from finance_research_lab.agent_models import ToolResult
from finance_research_lab.llm.chat_completions_client import ChatCompletionsClient
from finance_research_lab.models import RawNews, WatchlistItem
from finance_research_lab.news_trace import build_research_report
from finance_research_lab.research_agent import analyze_research_report_with_agent
from finance_research_lab.tools import trace_news_tool


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


def _report_payload(reasoning: str = "Agent generated strict report") -> dict[str, object]:
    return {
        "raw_news": {
            "headline": "AI capex increases",
            "source": "example",
            "url": "",
            "published_at": "",
            "body": "",
        },
        "event": {
            "event_type": "资本开支 / 产能扩张",
            "themes": ["AI", "数据中心"],
            "involved_entities": [],
            "key_facts": ["Agent fact"],
            "source_quality": "待复核",
            "confidence": "low",
            "reasoning": reasoning,
        },
        "value_chain": {
            "payer": "云厂商",
            "receiver": "光模块供应链",
            "chain_steps": ["AI CapEx", "数据中心", "光模块"],
            "impact_direction": "positive",
            "reasoning": "Agent chain reasoning",
        },
        "stock_impacts": [
            {
                "symbol": "300308.SZ",
                "name": "中际旭创",
                "market": "A股",
                "impact_type": "direct",
                "impact_strength": "high",
                "themes": ["AI", "光模块"],
                "reasoning": "Agent impact reasoning",
                "evidence": ["Watchlist match"],
                "risks": ["估值拥挤"],
                "verification_status": "unverified",
                "verification_source": "",
                "watchlist_hit": False,
            }
        ],
        "validation_tasks": [
            {"question": "查官方文件", "data_needed": "官方公告", "status": "pending"}
        ],
        "stage": "待判断",
        "action_state": "等验证",
    }


def _news() -> RawNews:
    return RawNews(
        headline="AI capex increases",
        source="Example News",
        url="https://news.example.com/ai-capex",
        published_at="2026-06-22T10:00:00Z",
        body="Microsoft increased AI data center spending and optical module demand.",
    )


def test_analyze_research_report_with_agent_returns_structured_report(tmp_path) -> None:
    requests: list[object] = []

    def fake_urlopen(request: object, timeout: int) -> FakeHTTPResponse:
        requests.append((request, timeout))
        return FakeHTTPResponse(_llm_payload(json.dumps(_report_payload())))

    report = analyze_research_report_with_agent(
        news=_news(),
        watchlist=[WatchlistItem("300308.SZ", "中际旭创", "A股", ("AI", "光模块"))],
        api_key="test-key",
        model="gpt-4o-mini",
        env_path=tmp_path / "missing.env",
        urlopen=fake_urlopen,
    )

    assert report.event.reasoning == "Agent generated strict report"
    assert report.raw_news == _news()
    assert report.stock_impacts[0].symbol == "300308.SZ"
    body = requests[0][0].data.decode("utf-8")
    assert '"type": "json_schema"' in body
    assert '"strict": true' in body


def test_analyze_research_report_with_agent_uses_custom_base_url() -> None:
    urls: list[str] = []

    def fake_urlopen(request: object, timeout: int) -> FakeHTTPResponse:
        urls.append(request.full_url)
        return FakeHTTPResponse(_llm_payload(json.dumps(_report_payload())))

    analyze_research_report_with_agent(
        news=_news(),
        watchlist=[WatchlistItem("300308.SZ", "中际旭创", "A股", ("AI", "光模块"))],
        api_key="test-key",
        model="agnes-2.0-flash",
        base_url="https://gateway.example.com/v1/",
        urlopen=fake_urlopen,
    )

    assert urls == ["https://gateway.example.com/v1/chat/completions"]


def test_chat_completions_client_reads_neutral_llm_config(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_API_KEY=test-key\n"
        "LLM_MODEL=test-model\n"
        "LLM_BASE_URL=https://gateway.example.com/v1/\n",
        encoding="utf-8",
    )

    client = ChatCompletionsClient(env_path=env_path)

    assert client.api_key == "test-key"
    assert client.model == "test-model"
    assert client.base_url == "https://gateway.example.com/v1"
    assert client.response_format == "json_schema"
    assert client.timeout_seconds == 60


def test_chat_completions_client_supports_deepseek_json_object_mode(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_API_KEY=test-key\n"
        "LLM_MODEL=deepseek-v4-pro\n"
        "LLM_BASE_URL=https://api.deepseek.com\n"
        "LLM_RESPONSE_FORMAT=json_object\n",
        encoding="utf-8",
    )
    requests: list[object] = []

    def fake_urlopen(request: object, timeout: int) -> FakeHTTPResponse:
        requests.append((request, timeout))
        return FakeHTTPResponse(_llm_payload(json.dumps(_report_payload())))

    client = ChatCompletionsClient(env_path=env_path, urlopen=fake_urlopen)
    response = client.structured_completion(
        messages=[{"role": "system", "content": "output json"}, {"role": "user", "content": "{}"}],
        schema_name="research_report",
        schema={"type": "object"},
    )

    body = json.loads(requests[0][0].data.decode("utf-8"))
    assert response.content
    assert requests[0][0].full_url == "https://api.deepseek.com/chat/completions"
    assert body["model"] == "deepseek-v4-pro"
    assert body["response_format"] == {"type": "json_object"}
    assert "json_schema" not in body["response_format"]
    assert "JSON Schema" in body["messages"][-1]["content"]
    assert "required" in body["messages"][-1]["content"]


def test_chat_completions_client_reads_timeout_config(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_API_KEY=test-key\n"
        "LLM_TIMEOUT_SECONDS=90\n",
        encoding="utf-8",
    )

    client = ChatCompletionsClient(env_path=env_path)

    assert client.timeout_seconds == 90


@pytest.mark.parametrize(
    "payload",
    [
        _llm_payload(refusal="Cannot comply"),
        _llm_payload("{not-json"),
    ],
)
def test_trace_news_tool_falls_back_when_agent_response_is_unusable(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    def fake_urlopen(request: object, timeout: int) -> FakeHTTPResponse:
        return FakeHTTPResponse(payload)

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    result = trace_news_tool(
        _news(),
        [WatchlistItem("300308.SZ", "中际旭创", "A股", ("AI", "数据中心", "光模块"))],
        urlopen=fake_urlopen,
    )

    assert isinstance(result, ToolResult)
    assert result.status == "success"
    assert "agent fallback" in result.error
    assert result.output == build_research_report(
        _news(),
        [WatchlistItem("300308.SZ", "中际旭创", "A股", ("AI", "数据中心", "光模块"))],
    )


def test_trace_news_tool_falls_back_when_api_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    result = trace_news_tool(
        _news(),
        [WatchlistItem("300308.SZ", "中际旭创", "A股", ("AI", "数据中心", "光模块"))],
        env_path=tmp_path / "missing.env",
    )

    assert result.status == "success"
    assert "LLM_API_KEY is not set" in result.error


def test_trace_news_tool_falls_back_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: int) -> FakeHTTPResponse:
        raise HTTPError("https://api.openai.com/v1/chat/completions", 500, "server", {}, None)

    monkeypatch.setenv("LLM_API_KEY", "test-key")

    result = trace_news_tool(
        _news(),
        [WatchlistItem("300308.SZ", "中际旭创", "A股", ("AI", "数据中心", "光模块"))],
        urlopen=fake_urlopen,
    )

    assert result.status == "success"
    assert "LLM request failed" in result.error
