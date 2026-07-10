from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, timedelta
from typing import Any

from .agent_models import ToolResult
from .agents.tools import ToolRegistry
from .llm.chat_completions_client import ChatCompletionsClient
from .models import RawNews, ResearchReport

MAX_TOOL_ROUNDS = 3
EVIDENCE_TOOL_NAMES = {
    "fetch_company_announcements",
    "fetch_financial_reports",
    "fetch_market_snapshot",
}


@dataclass(frozen=True)
class ToolCallingOutcome:
    results: tuple[ToolResult, ...]
    warnings: tuple[str, ...]
    attempted_tools: dict[str, frozenset[str]]


def run_evidence_tool_calls(
    client: ChatCompletionsClient,
    registry: ToolRegistry,
    news: RawNews,
    report: ResearchReport,
) -> ToolCallingOutcome:
    candidates = {impact.symbol for impact in report.stock_impacts if impact.market == "A股"}
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "你是受控投资研究 Agent。只调用能够验证候选影响的工具。"
                "每次调用都必须使用给出的候选代码；工具结果不足时可以补查，最多三轮。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "news": asdict(news),
                    "candidates": [asdict(impact) for impact in report.stock_impacts if impact.market == "A股"],
                },
                ensure_ascii=False,
            ),
        },
    ]
    results: list[ToolResult] = []
    completed_calls: dict[tuple[str, str], ToolResult] = {}
    warnings: list[str] = []
    attempted_tools: dict[str, set[str]] = {}
    tools = [tool for tool in registry.to_openai_tools() if tool["function"]["name"] in EVIDENCE_TOOL_NAMES]

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.tool_completion(messages=messages, tools=tools)
        calls = response.raw.get("tool_calls", []) if isinstance(response.raw, dict) else []
        if not calls:
            break
        messages.append({"role": "assistant", "content": response.content, "tool_calls": calls})
        for call in calls:
            key = _call_key(call)
            if key is not None and key in completed_calls:
                result = completed_calls[key]
            else:
                result = _execute_call(registry, call, candidates)
                if key is not None:
                    completed_calls[key] = result
            results.append(result)
            symbol = _call_symbol(call)
            name = str(call.get("function", {}).get("name", ""))
            if symbol in candidates and name in EVIDENCE_TOOL_NAMES:
                attempted_tools.setdefault(symbol, set()).add(name)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(call.get("id", "invalid-call")),
                    "content": json.dumps(_json_value(result.output, result.error), ensure_ascii=False),
                }
            )
            if result.status == "error":
                prefix = f"{symbol} " if symbol else ""
                warnings.append(f"{prefix}{result.tool_name} 不可用：{result.error}")
    else:
        warnings.append("已达到 3 轮工具调用上限，使用已有证据生成报告。")
    return ToolCallingOutcome(
        tuple(results),
        tuple(warnings),
        {symbol: frozenset(names) for symbol, names in attempted_tools.items()},
    )


def _call_symbol(call: dict[str, Any]) -> str:
    try:
        return str(json.loads(call.get("function", {}).get("arguments", "{}")).get("symbol", ""))
    except json.JSONDecodeError:
        return ""


def _call_key(call: dict[str, Any]) -> tuple[str, str] | None:
    function = call.get("function", {})
    name = str(function.get("name", ""))
    try:
        arguments = json.loads(function.get("arguments", "{}"))
    except json.JSONDecodeError:
        return None
    if not isinstance(arguments, dict):
        return None
    if name == "fetch_market_snapshot":
        arguments.setdefault("lookback_days", 5)
    elif name == "fetch_company_announcements":
        arguments.setdefault("start_date", "")
        arguments.setdefault("end_date", "")
    return name, json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _execute_call(registry: ToolRegistry, call: dict[str, Any], candidates: set[str]) -> ToolResult:
    function = call.get("function", {})
    name = function.get("name")
    if name not in EVIDENCE_TOOL_NAMES:
        return ToolResult(str(name or "unknown"), "error", None, "工具不在 Evidence 白名单中")
    try:
        arguments = json.loads(function.get("arguments", "{}"))
    except json.JSONDecodeError:
        return ToolResult(str(name), "error", None, "工具参数不是合法 JSON")
    if not isinstance(arguments, dict):
        return ToolResult(str(name), "error", None, "工具参数必须是 JSON object")
    error = _validate_arguments(str(name), arguments, candidates)
    if error:
        return ToolResult(str(name), "error", None, error)
    return registry.execute(str(name), arguments)


def _validate_arguments(name: str, arguments: dict[str, Any], candidates: set[str]) -> str:
    symbol = arguments.get("symbol")
    if not isinstance(symbol, str) or symbol not in candidates:
        return "symbol 必须是本次已校验的 A股候选"
    if name == "fetch_market_snapshot":
        lookback = arguments.get("lookback_days", 5)
        if not isinstance(lookback, int) or not 1 <= lookback <= 20:
            return "lookback_days 必须在 1 到 20 之间"
        arguments["lookback_days"] = lookback
    if name == "fetch_company_announcements":
        for key in ("start_date", "end_date"):
            if key not in arguments:
                arguments[key] = ""
        if not _valid_announcement_range(arguments["start_date"], arguments["end_date"]):
            return "公告日期必须是过去 90 天内的 YYYY-MM-DD"
    return ""


def _valid_announcement_range(start: Any, end: Any) -> bool:
    if not start and not end:
        return True
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except (TypeError, ValueError):
        return False
    return date.today() - timedelta(days=90) <= start_date <= end_date <= date.today()


def _json_value(output: Any, error: str) -> Any:
    if error:
        return {"error": error}
    if isinstance(output, tuple):
        return [asdict(item) if is_dataclass(item) else str(item) for item in output]
    if is_dataclass(output):
        return asdict(output)
    return output
