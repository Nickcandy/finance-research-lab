import json

from finance_research_lab.agents.tools import ToolRegistry, ToolSpec
from finance_research_lab.evidence_tool_agent import MAX_TOOL_ROUNDS, run_evidence_tool_calls
from finance_research_lab.llm.base import LLMResponse
from finance_research_lab.models import (
    EventAnalysis,
    MarketSnapshot,
    NewsItem,
    ResearchReport,
    StockImpact,
    ValueChainTrace,
)


class _Client:
    def __init__(self, calls):
        self.calls = list(calls)

    def tool_completion(self, **kwargs):
        del kwargs
        calls = self.calls.pop(0) if self.calls else []
        return LLMResponse("", "test", raw={"tool_calls": calls})


class _RepeatingClient:
    def tool_completion(self, **kwargs):
        del kwargs
        return LLMResponse("", "test", raw={"tool_calls": [_call("fetch_market_snapshot")]})


def test_tool_agent_records_empty_result_as_attempted_but_not_evidence() -> None:
    registry = _registry(announcements=())
    client = _Client([[_call("fetch_company_announcements")], []])

    outcome = run_evidence_tool_calls(client, registry, _news(), _report())

    assert outcome.results[0].status == "success"
    assert outcome.results[0].output == ()
    assert outcome.attempted_tools["300308.SZ"] == frozenset({"fetch_company_announcements"})


def test_tool_agent_rejects_symbol_outside_candidates() -> None:
    registry = _registry()
    client = _Client([[_call("fetch_market_snapshot", symbol="600519.SH")], []])

    outcome = run_evidence_tool_calls(client, registry, _news(), _report())

    assert outcome.results[0].status == "error"
    assert "本次已校验的 A股候选" in outcome.results[0].error
    assert outcome.attempted_tools == {}


def test_tool_agent_rejects_invalid_json_arguments() -> None:
    registry = _registry()
    call = _call("fetch_market_snapshot")
    call["function"]["arguments"] = "{invalid"

    outcome = run_evidence_tool_calls(_Client([[call], []]), registry, _news(), _report())

    assert outcome.results[0].status == "error"
    assert outcome.results[0].error == "工具参数不是合法 JSON"


def test_tool_agent_rejects_market_window_outside_limit() -> None:
    registry = _registry()
    call = _call("fetch_market_snapshot")
    call["function"]["arguments"] = json.dumps({"symbol": "300308.SZ", "lookback_days": 21})

    outcome = run_evidence_tool_calls(_Client([[call], []]), registry, _news(), _report())

    assert outcome.results[0].status == "error"
    assert "1 到 20" in outcome.results[0].error


def test_tool_agent_rejects_announcement_range_outside_ninety_days() -> None:
    registry = _registry()
    call = _call("fetch_company_announcements")
    call["function"]["arguments"] = json.dumps(
        {"symbol": "300308.SZ", "start_date": "2000-01-01", "end_date": "2000-01-02"}
    )

    outcome = run_evidence_tool_calls(_Client([[call], []]), registry, _news(), _report())

    assert outcome.results[0].status == "error"
    assert "过去 90 天" in outcome.results[0].error


def test_tool_agent_stops_after_three_rounds() -> None:
    calls = 0
    registry = _registry()
    original = registry.execute

    def execute(name, arguments):
        nonlocal calls
        calls += 1
        return original(name, arguments)

    registry.execute = execute
    outcome = run_evidence_tool_calls(_RepeatingClient(), registry, _news(), _report())

    assert len(outcome.results) == MAX_TOOL_ROUNDS
    assert calls == 1
    assert "已达到 3 轮工具调用上限" in outcome.warnings[-1]


def test_tool_agent_does_not_dedupe_different_arguments() -> None:
    calls = 0
    registry = _registry()
    original = registry.execute

    def execute(name, arguments):
        nonlocal calls
        calls += 1
        return original(name, arguments)

    registry.execute = execute
    first = _call("fetch_market_snapshot")
    second = _call("fetch_market_snapshot")
    second["function"]["arguments"] = json.dumps(
        {"lookback_days": 6, "symbol": "300308.SZ"}
    )

    outcome = run_evidence_tool_calls(_Client([[first, second], []]), registry, _news(), _report())

    assert len(outcome.results) == 2
    assert calls == 2


def test_tool_agent_dedupes_implicit_and_explicit_default_arguments() -> None:
    calls = 0
    registry = _registry()
    original = registry.execute

    def execute(name, arguments):
        nonlocal calls
        calls += 1
        return original(name, arguments)

    registry.execute = execute
    implicit = _call("fetch_market_snapshot")
    implicit["function"]["arguments"] = json.dumps({"symbol": "300308.SZ"})
    explicit = _call("fetch_market_snapshot")

    outcome = run_evidence_tool_calls(
        _Client([[implicit, explicit], []]), registry, _news(), _report()
    )

    assert len(outcome.results) == 2
    assert calls == 1


def _call(name: str, symbol: str = "300308.SZ") -> dict:
    arguments = {"symbol": symbol}
    if name == "fetch_market_snapshot":
        arguments["lookback_days"] = 5
    return {
        "id": f"call-{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def _registry(announcements=(object(),)) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_tool("fetch_company_announcements", lambda **kwargs: announcements))
    registry.register(_tool("fetch_financial_reports", lambda **kwargs: ()))
    registry.register(
        _tool(
            "fetch_market_snapshot",
            lambda **kwargs: MarketSnapshot(
                kwargs["symbol"],
                "2026-07-10",
                100,
                101,
                99,
                100,
                0,
                100,
                1000,
                kwargs.get("lookback_days", 5),
            ),
        )
    )
    return registry


def _tool(name, handler) -> ToolSpec:
    return ToolSpec(name, name, {"type": "object", "properties": {}}, handler)


def _news() -> NewsItem:
    return NewsItem("AI capex", "test", body="AI optical module demand")


def _report() -> ResearchReport:
    return ResearchReport(
        raw_news=_news(),
        event=EventAnalysis("资本开支"),
        value_chain=ValueChainTrace("cloud", "supplier"),
        stock_impacts=(StockImpact("300308.SZ", "中际旭创", "A股", "direct"),),
        validation_tasks=(),
        stage="验证",
        action_state="等验证",
    )
